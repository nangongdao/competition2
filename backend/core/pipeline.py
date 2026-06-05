"""Pipeline orchestration for ASR, translation, context, and revision."""

import asyncio
from typing import Awaitable, Callable, Optional

from loguru import logger

from core.config import settings
from models.segment import Segment
from services.asr_service import ASRService
from services.context_manager import ContextManager
from services.nmt_service import NMTService
from services.revision_service import RevisionService


MessageCallback = Callable[[dict], Awaitable[None]]


class Pipeline:
    """Coordinates the live interpretation flow for a single session."""

    def __init__(
        self,
        session_id: str,
        asr: ASRService,
        nmt: NMTService,
        ctx_manager: ContextManager,
        revision: Optional[RevisionService] = None,
    ) -> None:
        self.session_id = session_id
        self._asr = asr
        self._nmt = nmt
        self._ctx = ctx_manager
        self._revision = revision

        self._on_message: Optional[MessageCallback] = None
        self._sentence_count = 0
        self._running = False
        self._last_audio_at = 0.0
        self._silence_task: Optional[asyncio.Task[None]] = None

        self._asr.set_on_partial(self._handle_asr_partial)
        self._asr.set_on_final(self._handle_asr_final)

    def set_on_message(self, callback: MessageCallback) -> None:
        self._on_message = callback

    async def start(self) -> None:
        self._running = True
        await self._ctx.init_session(self.session_id)
        logger.info("Pipeline started for session {}", self.session_id)

    async def stop(self) -> None:
        self._running = False
        if self._silence_task:
            self._silence_task.cancel()
            self._silence_task = None
        await self._ctx.close_session(self.session_id)
        logger.info("Pipeline stopped for session {}", self.session_id)

    async def process_audio(self, audio_chunk: bytes) -> None:
        if not self._running:
            return

        loop = asyncio.get_running_loop()
        self._last_audio_at = loop.time()
        self._reset_silence_timer()
        await self._asr.process_chunk(audio_chunk)

    async def trigger_manual_revision(self) -> None:
        await self._check_revision(force=True, trigger_segment=None)

    async def _handle_asr_partial(self, text: str) -> None:
        if self._on_message:
            await self._on_message({
                "type": "asr_partial",
                "text": text,
            })

    async def _handle_asr_final(self, text: str, confidence: float) -> None:
        if not text.strip():
            return

        segment = Segment(
            id=f"{self.session_id}_{self._sentence_count}",
            text_asr=text,
            confidence=confidence,
            status="draft",
        )
        self._sentence_count += 1
        await self._ctx.add_segment(self.session_id, segment)
        await self._ctx.save_audio_chunk(
            self.session_id,
            segment.id,
            self._asr.get_last_audio_chunk(),
        )

        if self._on_message:
            await self._on_message({
                "type": "asr_final",
                "segment_id": segment.id,
                "text": segment.text_asr,
                "confidence": segment.confidence,
            })

        context_window = await self._ctx.get_window(self.session_id)

        async for token in self._nmt.translate_stream(context_window, segment):
            if not self._on_message:
                continue
            is_final = token == "<FINAL>"
            await self._on_message({
                "type": "translation_token",
                "segment_id": segment.id,
                "token": "" if is_final else token,
                "is_final": is_final,
            })

        segment.text_translated = self._nmt.last_translation
        segment.status = "final"
        await self._ctx.update_segment(self.session_id, segment)

        asr_revision = await self._revision.check_asr_correction(
            segment,
            context_window,
            self._nmt,
            self._asr,
        ) if self._revision else None

        if asr_revision:
            await self._ctx.update_source_text(
                self.session_id,
                asr_revision.segment_id,
                asr_revision.source_text or segment.text_asr,
            )
            await self._ctx.update_translation(
                self.session_id,
                asr_revision.segment_id,
                asr_revision.new_text,
            )
            if self._on_message:
                await self._on_message({
                    "type": "revision",
                    "segment_id": asr_revision.segment_id,
                    "new_text": asr_revision.new_text,
                    "source_text": asr_revision.source_text,
                    "reason": asr_revision.reason,
                })

        await self._check_revision(force=False, trigger_segment=segment)

    def _reset_silence_timer(self) -> None:
        if self._silence_task:
            self._silence_task.cancel()
        self._silence_task = asyncio.create_task(self._wait_for_silence())

    async def _wait_for_silence(self) -> None:
        try:
            await asyncio.sleep(settings.revision_silence_seconds)
            if not self._running:
                return

            now = asyncio.get_running_loop().time()
            if now - self._last_audio_at >= settings.revision_silence_seconds:
                await self._check_revision(force=True, trigger_segment=None)
        except asyncio.CancelledError:
            return

    async def _check_revision(
        self,
        force: bool,
        trigger_segment: Segment | None,
    ) -> None:
        if not self._revision or not settings.revision_enabled:
            return

        ambiguity_triggered = self._revision.has_semantic_ambiguity(trigger_segment)

        if not force and not ambiguity_triggered:
            should_trigger = (
                self._sentence_count > 0
                and self._sentence_count % settings.revision_trigger_sentences == 0
            )
            if not should_trigger:
                return

        context_window = await self._ctx.get_window(self.session_id)
        revisions = await self._revision.check_and_revise(
            context_window,
            self._nmt,
            force=force,
            trigger_segment=trigger_segment,
        )

        for rev in revisions:
            if self._on_message:
                await self._on_message({
                    "type": "revision",
                    "segment_id": rev.segment_id,
                    "new_text": rev.new_text,
                    "source_text": rev.source_text,
                    "reason": rev.reason,
                })
            if rev.source_text:
                await self._ctx.update_source_text(
                    self.session_id,
                    rev.segment_id,
                    rev.source_text,
                )
            await self._ctx.update_translation(
                self.session_id,
                rev.segment_id,
                rev.new_text,
            )
