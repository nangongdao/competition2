"""Revision service for translation and ASR correction."""

from __future__ import annotations

import hashlib
import re
import time
from collections import Counter, OrderedDict
from dataclasses import dataclass
from difflib import SequenceMatcher

from loguru import logger

from core.config import settings
from models.segment import ContextWindow, Segment
from services.asr_service import ASRService
from services.nmt_service import NMTService


@dataclass
class RevisionResult:
    segment_id: str
    new_text: str
    reason: str
    source_text: str | None = None
    old_text: str | None = None
    old_source_text: str | None = None
    correction_source: str | None = None
    trigger: str | None = None
    latency_ms: int | None = None
    confidence: float | None = None


class RevisionService:
    """Detects when prior translations or ASR text should be revised."""

    SIMILARITY_THRESHOLD = 0.80
    LENGTH_DIFF_THRESHOLD = 0.30
    CACHE_MAX_SIZE = 100
    AMBIGUOUS_PATTERNS = (
        re.compile(r"\b(it|they|he|she|this|that|which)\b", re.IGNORECASE),
        re.compile(r"\b(bank|run|set|point|right|left)\b", re.IGNORECASE),
    )
    ASR_CORRECTION_PROMPT = """You are an ASR post-editor for live English speech.

Given the local context, improve the current ASR sentence only if it has obvious transcription issues.
Return only one line.
- If the current sentence is already acceptable, return exactly: CORRECT
- Otherwise return the corrected English sentence
"""

    def __init__(self) -> None:
        self._revision_count = 0
        self._translation_cache: OrderedDict[str, str] = OrderedDict()
        self._context_fingerprint_by_segment: dict[str, str] = {}
        self._api_call_counts: Counter[str] = Counter()

    async def check_and_revise(
        self,
        context: ContextWindow,
        nmt: NMTService,
        *,
        force: bool = False,
        trigger_segment: Segment | None = None,
        trigger: str | None = None,
    ) -> list[RevisionResult]:
        revisions: list[RevisionResult] = []
        segments = context.get_all()
        revisable = segments[-settings.revision_max_window:-1]

        if len(revisable) < 2:
            return revisions

        context_text = context.to_context_text(max_sentences=settings.context_window_size)
        should_force_due_to_ambiguity = force or self._has_semantic_ambiguity(trigger_segment)

        for segment in revisable:
            context_fingerprint = self._compute_request_hash(segment.text_asr, context_text)
            cached_translation = self._translation_cache.get(context_fingerprint)

            if cached_translation is not None:
                self._api_call_counts["translation_cache_hit"] += 1
                if self._should_revise(segment.text_translated, cached_translation):
                    revisions.append(self._build_translation_revision(
                        segment,
                        cached_translation,
                        correction_source="translation_cache",
                        trigger=trigger,
                    ))
                continue

            if not should_force_due_to_ambiguity and self._can_skip_translation(
                segment,
                context_fingerprint,
            ):
                continue

            new_translation = await self._translate_segment(nmt, context, segment)
            if not new_translation:
                continue

            self._translation_cache[context_fingerprint] = new_translation
            self._translation_cache.move_to_end(context_fingerprint)
            self._trim_cache()
            self._context_fingerprint_by_segment[segment.id] = context_fingerprint

            if self._should_revise(segment.text_translated, new_translation):
                revisions.append(self._build_translation_revision(
                    segment,
                    new_translation,
                    correction_source="translation_window",
                    trigger=trigger,
                ))

        return revisions

    async def check_asr_correction(
        self,
        segment: Segment,
        context: ContextWindow,
        nmt: NMTService,
        asr: ASRService,
        audio_chunk: bytes | None = None,
        trigger: str = "low_confidence",
    ) -> RevisionResult | None:
        """Use context-aware post-editing to improve low-confidence ASR text."""
        if segment.confidence >= settings.asr_correction_confidence_threshold:
            return None

        started_at = time.perf_counter()
        correction_source = ""
        corrected = ""
        corrected_confidence: float | None = None

        if audio_chunk:
            self._api_call_counts["asr_redecode"] += 1
            redecode_result = await asr.redecode_audio(audio_chunk)
            if redecode_result and self._should_revise_source(segment.text_asr, redecode_result.text):
                corrected = redecode_result.text
                corrected_confidence = redecode_result.confidence
                correction_source = "audio_redecode"

        if not corrected:
            corrected = await self._post_edit_asr(segment, context, nmt)
            if not corrected:
                return None
            corrected_confidence = None
            correction_source = "llm_post_edit"

        if not self._should_revise_source(segment.text_asr, corrected):
            return None

        original_source = segment.text_asr
        original_translation = segment.text_translated
        segment.text_asr = corrected
        new_translation = await self._translate_segment(nmt, context, segment)
        if not new_translation:
            segment.text_asr = original_source
            return None

        segment.apply_revision(new_translation, "asr_correction")
        latency_ms = round((time.perf_counter() - started_at) * 1000)
        logger.info(
            "ASR correction triggered for {} via {} in {}ms: '{}' -> '{}'",
            segment.id,
            correction_source,
            latency_ms,
            original_source[:50],
            corrected[:50],
        )
        self._revision_count += 1
        return RevisionResult(
            segment_id=segment.id,
            new_text=new_translation,
            source_text=corrected,
            reason="asr_correction",
            old_text=original_translation,
            old_source_text=original_source,
            correction_source=correction_source,
            trigger=trigger,
            latency_ms=latency_ms,
            confidence=corrected_confidence,
        )

    @property
    def total_revisions(self) -> int:
        return self._revision_count

    def consume_api_call_counts(self) -> dict[str, int]:
        counts = dict(self._api_call_counts)
        self._api_call_counts.clear()
        return counts

    def has_semantic_ambiguity(self, segment: Segment | None) -> bool:
        return self._has_semantic_ambiguity(segment)

    def _build_translation_revision(
        self,
        segment: Segment,
        new_text: str,
        *,
        correction_source: str,
        trigger: str | None,
    ) -> RevisionResult:
        logger.info(
            "Translation revision triggered for {}: '{}' -> '{}'",
            segment.id,
            segment.text_translated[:50],
            new_text[:50],
        )
        old_translation = segment.text_translated
        segment.apply_revision(new_text, "translation_correction")
        self._revision_count += 1
        return RevisionResult(
            segment_id=segment.id,
            new_text=new_text,
            reason="translation_correction",
            old_text=old_translation,
            old_source_text=segment.text_asr,
            correction_source=correction_source,
            trigger=trigger,
            confidence=segment.confidence,
        )

    async def _translate_segment(
        self,
        nmt: NMTService,
        context: ContextWindow,
        segment: Segment,
    ) -> str:
        new_translation = ""
        try:
            self._api_call_counts["nmt_stream"] += 1
            async for token in nmt.translate_stream(context, segment):
                if token != "<FINAL>":
                    new_translation += token
        except Exception as exc:
            logger.warning("Revision translation failed for {}: {}", segment.id, exc)
            return ""

        return new_translation.strip()

    def _build_asr_prompt(self, segment: Segment, context: ContextWindow) -> str:
        segments = context.get_all()
        current_index = next(
            (index for index, item in enumerate(segments) if item.id == segment.id),
            -1,
        )

        before = segments[current_index - 1].text_asr if current_index > 0 else ""
        after = segments[current_index + 1].text_asr if 0 <= current_index < len(segments) - 1 else ""

        return f"""Previous sentence: "{before}"
Current sentence: "{segment.text_asr}"
Next sentence: "{after}"

Corrected:"""

    async def _post_edit_asr(
        self,
        segment: Segment,
        context: ContextWindow,
        nmt: NMTService,
    ) -> str:
        prompt = self._build_asr_prompt(segment, context)
        try:
            self._api_call_counts["nmt_complete"] += 1
            corrected = (await nmt.complete_text(
                prompt,
                system_prompt=self.ASR_CORRECTION_PROMPT,
            )).strip()
        except Exception as exc:
            logger.warning("ASR post-edit failed for {}: {}", segment.id, exc)
            return ""

        if not corrected or corrected == "CORRECT":
            return ""

        return corrected

    def _can_skip_translation(self, segment: Segment, context_fingerprint: str) -> bool:
        previous_fingerprint = self._context_fingerprint_by_segment.get(segment.id)
        has_same_context = previous_fingerprint == context_fingerprint
        has_high_confidence = segment.confidence >= 0.9
        return has_same_context and has_high_confidence

    def _should_revise(self, old_text: str, new_text: str) -> bool:
        if not old_text or not new_text:
            return False

        len_diff = abs(len(old_text) - len(new_text)) / max(len(old_text), len(new_text))
        if len_diff > self.LENGTH_DIFF_THRESHOLD:
            return True

        similarity = SequenceMatcher(None, old_text, new_text).ratio()
        return similarity < self.SIMILARITY_THRESHOLD

    def _should_revise_source(self, old_text: str, new_text: str) -> bool:
        old_normalized = self._normalize_source_text(old_text)
        new_normalized = self._normalize_source_text(new_text)
        return bool(old_normalized and new_normalized and old_normalized != new_normalized)

    def _normalize_source_text(self, text: str) -> str:
        normalized = re.sub(r"\s+", " ", text.strip().lower())
        return normalized.strip(" \t\r\n.,!?;:\"'")

    def _has_semantic_ambiguity(self, segment: Segment | None) -> bool:
        if segment is None:
            return False
        return any(pattern.search(segment.text_asr) for pattern in self.AMBIGUOUS_PATTERNS)

    def _compute_request_hash(self, text: str, context_text: str) -> str:
        digest = hashlib.md5(f"{text}|{context_text}".encode("utf-8")).hexdigest()
        return digest[:16]

    def _trim_cache(self) -> None:
        while len(self._translation_cache) > self.CACHE_MAX_SIZE:
            self._translation_cache.popitem(last=False)
