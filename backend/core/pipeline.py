"""Pipeline orchestration for ASR, translation, context, diagnostics, and revision."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Awaitable, Callable, Optional

from loguru import logger

from core.config import settings
from models.segment import Segment
from services.asr_service import ASRService
from services.context_manager import ContextManager
from services.nmt_service import NMTService
from services.revision_service import RevisionResult, RevisionService
from services.session_diagnostics import SessionDiagnostics
from services.language_config import (
    LanguageConfig,
    normalize_source_language,
    normalize_target_language,
)


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
        reconnect_token: str | None = None,
    ) -> None:
        self.session_id = session_id
        self._asr = asr
        self._nmt = nmt
        self._ctx = ctx_manager
        self._revision = revision
        self._reconnect_token = reconnect_token
        self._diagnostics = SessionDiagnostics(session_id=session_id)
        #: 说话人分离服务（默认关闭；开启时为每个 segment 标注 speaker_id）
        self._diarization = None
        if settings.diarization_enabled:
            from services.diarization_service import DiarizationService

            self._diarization = DiarizationService(
                similarity_threshold=settings.diarization_similarity_threshold,
            )
        self._language_config = LanguageConfig.from_values(
            settings.source_language,
            settings.target_language,
        )

        self._on_message: Optional[MessageCallback] = None
        self._sentence_count = 0
        self._running = False
        self._last_audio_at = 0.0
        self._last_diagnostics_emit_at = 0.0
        self._decode_window_started_at: float | None = None
        self._silence_task: Optional[asyncio.Task[None]] = None
        self._audio_worker_task: Optional[asyncio.Task[None]] = None
        self._audio_queue: asyncio.Queue[tuple[bytes, float]] = asyncio.Queue(
            maxsize=settings.audio_queue_max_chunks,
        )
        self._record_audio_queue_depth()

        #: 进行中的翻译任务，键为 segment_id，用于取消与等待
        self._translation_tasks: dict[str, asyncio.Task[None]] = {}
        #: 限制并发翻译数，避免瞬时打爆上游配额
        self._translation_semaphore = asyncio.Semaphore(
            settings.max_concurrent_translations,
        )
        #: 后台任务集合（如手动修正），用于 stop 时统一取消
        self._background_tasks: set[asyncio.Task[None]] = set()

        self._asr.set_on_partial(self._handle_asr_partial)
        self._asr.set_on_final(self._handle_asr_final)
        self._asr.set_language(self._language_config.source_language)

    def set_on_message(self, callback: MessageCallback) -> None:
        self._on_message = callback

    async def start(self) -> None:
        self._running = True
        reconnect_count = await self._ctx.init_session(self.session_id)
        self._diagnostics.set_reconnect_count(reconnect_count)
        self._audio_worker_task = asyncio.create_task(self._audio_worker())

        status_code = "SESSION_RECONNECTED" if reconnect_count else "SESSION_STARTED"
        status_message: dict = {
            "type": "status",
            "code": status_code,
            "message": f"Session {self.session_id} is ready",
            "session_id": self.session_id,
        }
        # 下发重连令牌，客户端在重连时以此证明会话所有权。
        if self._reconnect_token:
            status_message["reconnect_token"] = self._reconnect_token
        await self._emit(status_message)
        await self._emit_diagnostics()
        self._last_diagnostics_emit_at = asyncio.get_running_loop().time()
        logger.info("Pipeline started for session {}", self.session_id)

    async def stop(self) -> None:
        self._running = False
        if self._silence_task:
            self._silence_task.cancel()
            self._silence_task = None

        if self._audio_worker_task:
            self._audio_worker_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._audio_worker_task
            self._audio_worker_task = None

        # 给在途翻译一个短暂的收尾窗口，超时则取消
        if self._translation_tasks:
            pending = list(self._translation_tasks.values())
            done, still_pending = await asyncio.wait(pending, timeout=3.0)
            for task in still_pending:
                task.cancel()
            await asyncio.gather(*still_pending, return_exceptions=True)

        # 取消未完成的临时后台任务（如手动修正）
        if self._background_tasks:
            tasks = list(self._background_tasks)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self._background_tasks.clear()

        self._record_audio_queue_depth()
        self._asr.reset_session_state()
        self._diagnostics.finish()
        await self._emit_diagnostics()
        await self._ctx.close_session(self.session_id)
        logger.info("Pipeline stopped for session {}", self.session_id)

    async def wait_for_pending_translations(self, timeout: float = 5.0) -> None:
        """等待在途翻译任务完成（测试与优雅关停使用）。"""
        pending = [
            task
            for task in self._translation_tasks.values()
            if not task.done()
        ]
        if not pending:
            return
        await asyncio.wait(pending, timeout=timeout)

    async def process_audio(self, audio_chunk: bytes) -> None:
        if not self._running:
            return

        received_at = asyncio.get_running_loop().time()
        self._diagnostics.record_audio_chunk(len(audio_chunk))

        try:
            self._audio_queue.put_nowait((audio_chunk, received_at))
            self._record_audio_queue_depth()
            await self._emit_periodic_diagnostics(received_at)
        except asyncio.QueueFull:
            self._diagnostics.record_dropped_audio_chunk()
            self._record_audio_queue_depth()
            logger.warning(
                "Dropping audio chunk for {} because queue is full",
                self.session_id,
            )
            await self._emit({
                "type": "status",
                "code": "AUDIO_QUEUE_FULL",
                "message": "Audio input is arriving faster than it can be processed",
                "session_id": self.session_id,
            })
            await self._emit_diagnostics()

    async def trigger_manual_revision(self) -> None:
        """手动触发一次全文修正。

        修正会调用上游 LLM，可能耗时数秒，不能阻塞控制消息接收循环，
        因此丢给后台任务执行，并由 stop() 统一取消。
        """
        task = asyncio.create_task(
            self._check_revision(force=True, trigger_segment=None, trigger="manual"),
            name=f"manual-revision-{self.session_id}",
        )
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        await self._emit_diagnostics()

    async def emit_diagnostics(self) -> None:
        await self._emit_diagnostics()

    @property
    def language_config(self) -> LanguageConfig:
        return self._language_config

    async def update_glossary(self, entries: list[dict]) -> None:
        """更新会话术语表（领域自适应）。

        Args:
            entries: 术语表条目字典列表，形如
                [{"source": "K8s", "target": "Kubernetes", "keep_original": false}, ...]。
        """
        from services.glossary import parse_glossary_json

        parsed = parse_glossary_json(entries)
        self._nmt.set_glossary(parsed)
        await self._emit({
            "type": "status",
            "code": "GLOSSARY_UPDATED",
            "message": f"Glossary updated with {len(parsed)} entries",
            "session_id": self.session_id,
        })

    async def update_config(
        self,
        *,
        language: object | None = None,
        target_language: object | None = None,
    ) -> None:
        source = (
            normalize_source_language(language)
            if language is not None
            else self._language_config.source_language
        )
        target = (
            normalize_target_language(target_language)
            if target_language is not None
            else self._language_config.target_language
        )
        self._language_config = LanguageConfig(
            source_language=source,
            target_language=target,
        )
        self._asr.set_language(self._language_config.source_language)
        await self._emit({
            "type": "status",
            "code": "CONFIG_UPDATED",
            "message": (
                "Language config updated: "
                f"{self._language_config.source_label} -> "
                f"{self._language_config.target_label}"
            ),
            "session_id": self.session_id,
            "source_language": self._language_config.source_language,
            "target_language": self._language_config.target_language,
        })

    async def _audio_worker(self) -> None:
        while True:
            audio_chunk, received_at = await self._audio_queue.get()
            try:
                self._record_audio_queue_depth()
                queue_wait_ms = round((asyncio.get_running_loop().time() - received_at) * 1000)
                self._diagnostics.record_audio_queue_wait(queue_wait_ms)
                await self._process_audio_now(audio_chunk, received_at)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Audio worker failed for {}: {}", self.session_id, exc)
            finally:
                self._audio_queue.task_done()

    async def _process_audio_now(self, audio_chunk: bytes, received_at: float) -> None:
        if not self._running:
            return

        loop = asyncio.get_running_loop()
        self._last_audio_at = loop.time()
        if self._decode_window_started_at is None:
            self._decode_window_started_at = received_at

        self._reset_silence_timer()
        emitted_segments = await self._asr.process_chunk(audio_chunk)
        if emitted_segments:
            self._decode_window_started_at = None

    async def _handle_asr_partial(self, text: str) -> None:
        await self._emit({
            "type": "asr_partial",
            "text": text,
        })

    async def _handle_asr_final(self, text: str, confidence: float) -> None:
        """ASR 出最终结果的回调。

        只做轻量工作（落库 + 广播 ASR 结果），翻译与修正交给后台任务，
        避免阻塞 ASR 处理下一句 —— 这是延迟不累积的关键。
        """
        if not text.strip():
            return

        loop = asyncio.get_running_loop()
        asr_final_at = loop.time()
        capture_to_asr_ms = None
        if self._decode_window_started_at is not None:
            capture_to_asr_ms = round((asr_final_at - self._decode_window_started_at) * 1000)

        segment_index = await self._ctx.next_segment_index(self.session_id)
        segment = Segment(
            id=f"{self.session_id}_{segment_index}",
            text_asr=text,
            confidence=confidence,
            source_language=self._language_config.source_language,
            target_language=self._language_config.target_language,
            status="draft",
        )
        self._sentence_count += 1
        self._diagnostics.record_asr_segment(capture_to_asr_ms)

        segment_audio = self._asr.get_last_audio_chunk()
        # 说话人分离：先识别并标注，再落库，保证 speaker_id 持久化
        if self._diarization is not None:
            import numpy as np

            samples = np.frombuffer(segment_audio, dtype=np.float32) if segment_audio else np.empty(0)
            segment.speaker_id = self._diarization.identify(samples)

        await self._ctx.add_segment(self.session_id, segment)
        await self._ctx.save_audio_chunk(
            self.session_id,
            segment.id,
            segment_audio,
        )

        await self._emit({
            "type": "asr_final",
            "segment_id": segment.id,
            "segment_index": segment_index,
            "text": segment.text_asr,
            "confidence": segment.confidence,
            "latency_ms": capture_to_asr_ms,
            "source_language": segment.source_language,
            "target_language": segment.target_language,
            "speaker_id": segment.speaker_id,
        })

        # 翻译链路异步化：立即返回，不阻塞下一句 ASR
        task = asyncio.create_task(
            self._translate_and_revise(segment, asr_final_at),
            name=f"translate-{segment.id}",
        )
        self._translation_tasks[segment.id] = task
        task.add_done_callback(
            lambda finished: self._translation_tasks.pop(segment.id, None)
        )

    async def _translate_and_revise(self, segment: Segment, asr_final_at: float) -> None:
        """后台执行翻译与修正。

        Args:
            segment: 待翻译的语音片段。
            asr_final_at: ASR 出结果的时刻，用于计算端到端延迟。
        """
        async with self._translation_semaphore:
            try:
                await self._run_translation(segment, asr_final_at)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Translation failed for {}: {}", segment.id, exc)
                # 降级：至少让用户看到原文（配合 ARCH-02 的重试+降级）
                await self._emit({
                    "type": "translation_token",
                    "segment_id": segment.id,
                    "segment_index": self._segment_index_of(segment),
                    "token": f"[未翻译] {segment.text_asr}",
                    "is_final": True,
                })

            try:
                await self._run_revision(segment)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Revision failed for {}: {}", segment.id, exc)
            finally:
                await self._emit_diagnostics()

    async def _run_translation(self, segment: Segment, asr_final_at: float) -> None:
        """流式翻译单个片段并落库。"""
        loop = asyncio.get_running_loop()
        context_window = await self._ctx.get_window(self.session_id)
        translated_parts: list[str] = []
        first_token_latency_ms: int | None = None

        async for token in self._nmt.translate_stream(context_window, segment):
            is_final = token == "<FINAL>"
            if not is_final:
                if first_token_latency_ms is None:
                    first_token_latency_ms = round((loop.time() - asr_final_at) * 1000)
                translated_parts.append(token)

            await self._emit({
                "type": "translation_token",
                "segment_id": segment.id,
                "segment_index": self._segment_index_of(segment),
                "token": "" if is_final else token,
                "is_final": is_final,
            })

        translation_final_latency_ms = round((loop.time() - asr_final_at) * 1000)
        segment.text_translated = "".join(translated_parts).strip()
        segment.status = "final"
        self._diagnostics.record_translation_segment(
            first_token_latency_ms=first_token_latency_ms,
            final_latency_ms=translation_final_latency_ms,
        )
        await self._ctx.update_segment(self.session_id, segment)

    async def _run_revision(self, segment: Segment) -> None:
        """对单个片段执行 ASR 修正与周期性的译文润色。"""
        if not self._revision:
            return

        context_window = await self._ctx.get_window(self.session_id)
        cached_audio = await self._ctx.get_audio_chunk(self.session_id, segment.id)
        asr_revision = await self._revision.check_asr_correction(
            segment,
            context_window,
            self._nmt,
            self._asr,
            audio_chunk=cached_audio,
            trigger="low_confidence",
        )
        self._consume_revision_api_counts()

        if asr_revision:
            self._record_revision(asr_revision)
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
            await self._emit(self._revision_to_message(asr_revision))

        await self._check_revision(force=False, trigger_segment=segment, trigger="asr_final")

    @staticmethod
    def _segment_index_of(segment: Segment) -> int:
        """从 segment.id 解析单调递增的片段序号。

        segment.id 形如 "{session_id}_{index}"，序号恒为末段，直接复用。
        """
        try:
            return int(segment.id.rsplit("_", 1)[-1])
        except (ValueError, IndexError):
            return 0

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
                await self._check_revision(force=True, trigger_segment=None, trigger="silence")
                await self._emit_diagnostics()
        except asyncio.CancelledError:
            return

    async def _check_revision(
        self,
        force: bool,
        trigger_segment: Segment | None,
        trigger: str,
    ) -> None:
        if not self._revision or not settings.revision_enabled:
            return

        ambiguity_triggered = self._revision.has_semantic_ambiguity(trigger_segment)
        active_trigger = trigger

        if not force and not ambiguity_triggered:
            should_trigger = (
                self._sentence_count > 0
                and self._sentence_count % settings.revision_trigger_sentences == 0
            )
            if not should_trigger:
                return
            active_trigger = "sentence_count"
        elif ambiguity_triggered:
            active_trigger = "semantic_ambiguity"

        context_window = await self._ctx.get_window(self.session_id)
        revisions = await self._revision.check_and_revise(
            context_window,
            self._nmt,
            force=force,
            trigger_segment=trigger_segment,
            trigger=active_trigger,
        )
        self._consume_revision_api_counts()

        for rev in revisions:
            self._record_revision(rev)
            await self._emit(self._revision_to_message(rev))
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

    def _consume_revision_api_counts(self) -> None:
        if not self._revision:
            return
        for name, count in self._revision.consume_api_call_counts().items():
            self._diagnostics.record_api_call(name, count)

    def _record_revision(self, revision: RevisionResult) -> None:
        self._diagnostics.record_revision(
            reason=revision.reason,
            source=revision.correction_source,
            trigger=revision.trigger,
            latency_ms=revision.latency_ms,
        )

    async def _emit_diagnostics(self) -> None:
        await self._emit({
            "type": "session_diagnostics",
            "diagnostics": self._diagnostics.snapshot(),
        })

    async def _emit_periodic_diagnostics(self, now: float) -> None:
        if now - self._last_diagnostics_emit_at < settings.diagnostics_emit_interval_seconds:
            return

        self._last_diagnostics_emit_at = now
        await self._emit_diagnostics()

    async def _emit(self, message: dict) -> None:
        if self._on_message:
            await self._on_message(message)

    def _record_audio_queue_depth(self) -> None:
        self._diagnostics.record_audio_queue_depth(
            self._audio_queue.qsize(),
            self._audio_queue.maxsize,
        )

    def _revision_to_message(self, revision: RevisionResult) -> dict:
        message = {
            "type": "revision",
            "segment_id": revision.segment_id,
            "new_text": revision.new_text,
            "source_text": revision.source_text,
            "reason": revision.reason,
            "old_text": revision.old_text,
            "old_source_text": revision.old_source_text,
            "correction_source": revision.correction_source,
            "trigger": revision.trigger,
            "latency_ms": revision.latency_ms,
            "confidence": revision.confidence,
        }
        return {key: value for key, value in message.items() if value is not None}
