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
from services.translation_memory import build_language_pair
from services.session_diagnostics import SessionDiagnostics
from services.tts_service import TTSService
from services.language_config import (
    LanguageConfig,
    detected_language_to_source_code,
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
        tts: Optional[TTSService] = None,
        reconnect_token: str | None = None,
    ) -> None:
        self.session_id = session_id
        self._asr = asr
        self._nmt = nmt
        self._ctx = ctx_manager
        self._revision = revision
        self._tts = tts
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
        self._on_message_bytes: Optional[Callable[[bytes], Awaitable[None]]] = None
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

        #: 翻译记忆库（V5.3）：会话级实例，翻译完成写回、相似句直接复用；
        #: V5.3 生产化补全——绑定全局持久化存储实现跨会话累积。
        from services.translation_memory import TranslationMemoryService
        from services.translation_memory_store import get_tm_store

        self._translation_memory = TranslationMemoryService(
            session_id=session_id,
            similarity_threshold=settings.translation_memory_threshold,
        )
        self._translation_memory.attach_store(get_tm_store())
        self._nmt.attach_translation_memory(self._translation_memory)

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

    def set_on_message_bytes(self, callback: Callable[[bytes], Awaitable[None]]) -> None:
        """注册二进制帧回调（如 TTS 音频）。"""
        self._on_message_bytes = callback

    async def start(self) -> None:
        self._running = True
        reconnect_count = await self._ctx.init_session(self.session_id)
        self._diagnostics.set_reconnect_count(reconnect_count)
        self._audio_worker_task = asyncio.create_task(self._audio_worker())

        # 阶段 10 可观测性补全：会话台账记录开始时间
        try:
            from services.session_data_service import get_session_data_service

            service = get_session_data_service()
            if service is not None:
                service.record_session_start(self.session_id)
        except Exception as exc:
            logger.warning("Failed to record session start for {}: {}", self.session_id, exc)

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
        # 阶段 10 可观测性补全：会话质量指标随会话落盘（历史面板可回看）
        self._persist_session_quality()
        await self._ctx.close_session(self.session_id)
        logger.info("Pipeline stopped for session {}", self.session_id)

    def _persist_session_quality(self) -> None:
        """把本次会话质量指标写入会话台账（仅当台账服务已初始化）。"""
        try:
            from services.session_data_service import get_session_data_service

            service = get_session_data_service()
            if service is None:
                return
            snapshot = self._diagnostics.snapshot()
            quality = {
                "asr_segments": snapshot.get("asr_segments", 0),
                "translation_segments": snapshot.get("translation_segments", 0),
                "revision_segments": snapshot.get("revision_segments", 0),
                "audio_chunks_received": snapshot.get("audio_chunks_received", 0),
                "audio_chunks_dropped": snapshot.get("audio_chunks_dropped", 0),
                "audio_queue_max_depth": snapshot.get("audio_queue_max_depth", 0),
                "audio_queue_capacity": snapshot.get("audio_queue_capacity", 0),
                "reconnect_count": snapshot.get("reconnect_count", 0),
                "latency": snapshot.get("latency", {}),
                "api_call_counts": snapshot.get("api_call_counts", {}),
            }
            service.update_session_quality(self.session_id, quality)
            service.update_session_progress(
                self.session_id,
                segment_count=snapshot.get("translation_segments", 0),
                duration_ms=snapshot.get("duration_ms", 0),
            )
        except Exception as exc:
            logger.warning(
                "Failed to persist session quality for {}: {}",
                self.session_id,
                exc,
            )

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

    @property
    def nmt_style_preset(self) -> str:
        """当前翻译风格预设（透传 NMT 服务的风格名）。"""
        return self._nmt.style_preset

    def translation_memory_stats(self) -> dict[str, object] | None:
        """返回本会话翻译记忆库统计（未启用时为 None）。"""
        tm = getattr(self, "_translation_memory", None)
        if tm is None:
            return None
        return tm.stats

    def clear_translation_memory(self) -> bool:
        """清空本会话翻译记忆库。

        Returns:
            是否实际清空（未启用返回 False）。
        """
        tm = getattr(self, "_translation_memory", None)
        if tm is None:
            return False
        tm.clear()
        return True

    async def update_glossary(self, entries: list[dict]) -> None:
        """更新会话术语表（领域自适应）。

        Args:
            entries: 术语表条目字典列表，形如
                [{"source": "K8s", "target": "Kubernetes", "keep_original": false}, ...]。
        """
        from services.glossary import parse_glossary_json

        parsed = parse_glossary_json(entries)
        self._nmt.set_glossary(parsed)
        # 阶段 2：术语热词注入 ASR —— 术语 source 同时作为 ASR 热词提示，
        # 从识别源头降低技术术语/品牌名误识别率（NMT 侧无法修正已错识别的词）。
        hotwords = [entry.source for entry in parsed if entry.source]
        self._asr.set_hotwords(hotwords)
        await self._emit({
            "type": "status",
            "code": "GLOSSARY_UPDATED",
            "message": f"Glossary updated with {len(parsed)} entries",
            "session_id": self.session_id,
            "asr_hotwords": len(hotwords),
        })

    async def update_config(
        self,
        *,
        language: object | None = None,
        target_language: object | None = None,
        style_preset: object | None = None,
        asr_hotwords_enabled: object | None = None,
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
        if style_preset is not None:
            self._nmt.set_style_preset(style_preset)
        if asr_hotwords_enabled is not None:
            self._asr.set_hotwords_enabled(bool(asr_hotwords_enabled))
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
            "style_preset": self._nmt.style_preset,
            "asr_hotwords_enabled": self._asr.hotwords_enabled,
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

    async def _handle_asr_final(self, text: str, confidence: float, detected_language: str | None = None) -> None:
        """ASR 出最终结果的回调。

        只做轻量工作（落库 + 广播 ASR 结果），翻译与修正交给后台任务，
        避免阻塞 ASR 处理下一句 —— 这是延迟不累积的关键。

        Args:
            text: ASR 识别文本。
            confidence: 置信度。
            detected_language: auto 模式下 Whisper 检测到的语言名/代码；
                非 auto 模式为 None。
        """
        if not text.strip():
            return

        loop = asyncio.get_running_loop()
        asr_final_at = loop.time()
        capture_to_asr_ms = None
        if self._decode_window_started_at is not None:
            capture_to_asr_ms = round((asr_final_at - self._decode_window_started_at) * 1000)

        # 源语言自动检测（阶段 8）：auto 模式下用 Whisper 检测结果修正
        # 会话源语言，使后续 NMT 翻译语言对正确（英→中 vs 日→中等）。
        detected_source: str | None = None
        if self._language_config.source_language == "auto" and detected_language:
            detected_source = detected_language_to_source_code(detected_language)
            if detected_source:
                self._language_config = LanguageConfig(
                    source_language=detected_source,
                    target_language=self._language_config.target_language,
                )
                self._asr.set_language(detected_source)

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

        # 商用成本模型：记录本次 ASR 处理音频时长（尽力而为）
        self._record_asr_cost(capture_to_asr_ms)

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
            # 阶段 8：auto 模式下 Whisper 检测到的源语言代码（如 en/ja/zh-CN）
            "detected_language": detected_source,
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

        # 商用成本模型：记录本次 NMT 用量（基于文本长度估算 token）
        self._record_nmt_cost(segment)

        # 付费订阅（V5.5）：翻译完成即消耗一次每日配额（尽力而为，超限不中断）
        self._consume_subscription_quota()

        # 翻译记忆库（V5.3）：翻译完成的句对写回索引，供后续相似句复用
        self._nmt.record_translation(segment, segment.text_translated)

        # 后端 TTS：译文 final 后异步合成语音并下发（不阻塞翻译管线）。
        # 合成失败静默降级（不发 tts_audio），前端仍可正常显示字幕。
        if self._tts and self._tts.enabled and segment.text_translated:
            await self._emit_tts_audio(segment)

    def _consume_subscription_quota(self) -> None:
        """消耗一次订阅配额（V5.5，尽力而为）。

        配额超限时翻译不中断（同传稳定性优先），仅记录日志；
        前端通过订阅面板展示剩余额度与升级提示。
        """
        try:
            from services.subscription import get_subscription_service

            service = get_subscription_service()
            if service is None:
                return
            snapshot = service.consume()
            if snapshot.get("daily_remaining") is not None and snapshot["daily_remaining"] <= 0:
                logger.warning(
                    "Session {} reached daily translation quota ({}/{})",
                    self.session_id,
                    snapshot.get("daily_used"),
                    snapshot.get("daily_limit"),
                )
        except Exception as exc:
            logger.error("Failed to consume subscription quota: {}", exc)

    def _record_nmt_cost(self, segment: Segment) -> None:
        """记录本次 NMT 翻译用量到成本模型（尽力而为，不影响主链路）。

        输入 token 按源句 + 上下文粗估，输出 token 按译文长度粗估。
        """
        try:
            from services.cost_service import (
                CostUsage,
                estimate_tokens,
                get_cost_service,
            )

            service = get_cost_service()
            if service is None:
                return
            usage = CostUsage(
                nmt_input_tokens=estimate_tokens(segment.text_asr),
                nmt_output_tokens=estimate_tokens(segment.text_translated or ""),
            )
            service.record(usage)
        except Exception as exc:
            logger.error("Failed to record NMT cost: {}", exc)

    def _record_asr_cost(self, decode_ms: int | None) -> None:
        """记录本次 ASR 处理音频时长到成本模型（尽力而为）。

        Args:
            decode_ms: 本句解码窗口时长（毫秒）；None 时忽略。
        """
        if decode_ms is None or decode_ms <= 0:
            return
        try:
            from services.cost_service import get_cost_service

            service = get_cost_service()
            if service is None:
                return
            service.record_asr(decode_ms / 1000.0)
        except Exception as exc:
            logger.error("Failed to record ASR cost: {}", exc)

    async def _emit_tts_audio(self, segment: Segment) -> None:
        """合成译文语音并通过 `tts_audio` 文本帧 + 二进制帧下发。

        协议：先发一条 JSON 元信息帧（包含 segment_id / format / sample_rate），
        随后立即发送 MP3 二进制帧；前端据此播放。
        失败时发送空音频（bytes 空），前端静默忽略。
        """
        if not self._tts:
            return

        try:
            audio = await self._tts.synthesize(
                segment.text_translated,
                language=segment.target_language,
            )
        except Exception as exc:
            logger.error("TTS emit failed for {}: {}", segment.id, exc)
            return

        await self._emit({
            "type": "tts_audio",
            "segment_id": segment.id,
            "segment_index": self._segment_index_of(segment),
            "format": "mp3",
            "length": len(audio),
        })
        await self._emit_bytes(audio)

    async def _emit_bytes(self, payload: bytes) -> None:
        """发送二进制帧（若回调支持）。"""
        if self._on_message_bytes:
            await self._on_message_bytes(payload)

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
            # 修正后的译文写回翻译记忆库（越用越准）：ASR 修正同时更新了
            # 源句与译文，记忆库中的旧句对已过时，用修正结果覆盖以提升未来命中质量。
            self._record_revised_translation_memory(asr_revision)
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
            # 译文修正（润色）后写回翻译记忆库，使修正结果跨会话复用。
            self._record_revised_translation_memory(rev)

    def _record_revised_translation_memory(self, revision: RevisionResult) -> None:
        """把修正后的译文写回翻译记忆库。

        初始翻译在 _run_translation 中已写入记忆库；当修正引擎随后对译文
        进行润色/纠错时，旧句对中的译文已过时。若不更新，后续会话仍会
        命中低质量译文，与「翻过的句子越用越准」的目标相悖。

        Args:
            revision: 已完成的修正结果（含源句与最终译文）。
        """
        if not revision or not revision.new_text:
            return
        tm = getattr(self, "_translation_memory", None)
        if tm is None:
            return
        source_text = revision.source_text or revision.old_source_text
        if not source_text or not source_text.strip():
            return
        try:
            tm.add(source_text, revision.new_text, language_pair=build_language_pair(
                self._language_config.source_language,
                self._language_config.target_language,
            ))
        except Exception as exc:
            # 记忆库写入失败不应影响修正链路（尽力而为）
            logger.debug("Translation memory update on revision failed: {}", exc)

    def _consume_revision_api_counts(self) -> None:
        if not self._revision:
            return
        for name, count in self._revision.consume_api_call_counts().items():
            self._diagnostics.record_api_call(name, count)
        # 阶段 4：防循环/限流的跳过计数也纳入诊断可观测
        for name, count in self._revision.consume_skipped_counts().items():
            self._diagnostics.record_api_call(f"revision_skipped_{name}", count)

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
