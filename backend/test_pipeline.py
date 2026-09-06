from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from typing import Awaitable, Callable, Optional

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.config import settings
from core.pipeline import Pipeline
from models.segment import ContextWindow, Segment


FinalCallback = Callable[[str, float, str | None], Awaitable[None]]
PartialCallback = Callable[[str], Awaitable[None]]


class FakeASRService:
    def __init__(
        self,
        *,
        final_text: str | None = None,
        confidence: float = 0.9,
        processed_event: asyncio.Event | None = None,
        detected_language: str | None = None,
    ) -> None:
        self.final_text = final_text
        self.confidence = confidence
        self.processed_event = processed_event
        self.detected_language = detected_language
        self.processed_chunks: list[bytes] = []
        self.reset_calls = 0
        self.language_updates: list[str] = []
        self._on_partial: Optional[PartialCallback] = None
        self._on_final: Optional[FinalCallback] = None
        self._last_audio_chunk = b""
        # 热词（阶段 2）：记录注入调用便于断言
        self.hotword_updates: list[list[str]] = []
        self.hotwords_enabled = True

    async def wait_until_processed(self, count: int, timeout: float = 1.0) -> None:
        """轮询等待音频缓冲被处理到指定次数。"""
        deadline = asyncio.get_running_loop().time() + timeout
        while len(self.processed_chunks) < count:
            if asyncio.get_running_loop().time() >= deadline:
                raise AssertionError(
                    f"Timed out waiting for {count} processed chunks; "
                    f"got {len(self.processed_chunks)}"
                )
            await asyncio.sleep(0.01)

    def set_on_partial(self, callback: PartialCallback) -> None:
        self._on_partial = callback

    def set_on_final(self, callback: FinalCallback) -> None:
        self._on_final = callback

    def set_language(self, source_language: str) -> None:
        self.language_updates.append(source_language)

    def set_hotwords(self, hotwords: list[str]) -> None:
        self.hotword_updates.append(list(hotwords))

    def set_hotwords_enabled(self, enabled: bool) -> None:
        self.hotwords_enabled = bool(enabled)

    async def process_chunk(self, audio_bytes: bytes) -> int:
        self.processed_chunks.append(audio_bytes)
        self._last_audio_chunk = audio_bytes

        emitted = 0
        if self.final_text and self._on_final:
            await self._on_final(self.final_text, self.confidence, self.detected_language)
            emitted = 1

        if self.processed_event:
            self.processed_event.set()
        return emitted

    def get_last_audio_chunk(self) -> bytes:
        return self._last_audio_chunk

    def reset_session_state(self) -> None:
        self.reset_calls += 1
        self._on_partial = None
        self._on_final = None


class FakeNMTService:
    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens
        self.translation_calls = 0
        self.segments: list[Segment] = []
        self.recorded_pairs: list[tuple[str, str]] = []
        self.style_preset = "concise"
        self.glossary_updates: list[list[object]] = []

    def set_style_preset(self, style: object) -> None:
        from services.translation_style import normalize_style_preset

        self.style_preset = normalize_style_preset(style)

    def set_glossary(self, entries: list[object]) -> None:
        self.glossary_updates.append(list(entries))

    async def translate_stream(self, context: ContextWindow, current: Segment):
        self.translation_calls += 1
        self.segments.append(current)
        self.last_context = context

        for token in self.tokens:
            yield token
        yield "<FINAL>"

    def attach_translation_memory(self, tm) -> None:
        self.tm = tm

    def record_translation(self, current: Segment, translated: str) -> None:
        self.recorded_pairs.append((current.text_asr, translated))

    def translation_memory_stats(self):
        return None


class BlockingNMTService(FakeNMTService):
    """翻译时先等待 release_event 再产出 token，用于模拟慢翻译。"""

    def __init__(self, tokens: list[str], release_event: asyncio.Event) -> None:
        super().__init__(tokens)
        self.release_event = release_event

    async def translate_stream(self, context: ContextWindow, current: Segment):
        self.translation_calls += 1
        self.segments.append(current)
        await self.release_event.wait()
        for token in self.tokens:
            yield token
        yield "<FINAL>"


class FakeContextManager:
    def __init__(self, *, reconnect_count: int = 0) -> None:
        self.reconnect_count = reconnect_count
        self.window = ContextWindow(session_id="test-session", window_size=10)
        self.segment_index = 0
        self.saved_audio: dict[str, bytes] = {}
        self.closed_sessions: list[str] = []

    async def init_session(self, session_id: str) -> int:
        self.window.session_id = session_id
        return self.reconnect_count

    async def next_segment_index(self, _session_id: str) -> int:
        current = self.segment_index
        self.segment_index += 1
        return current

    async def add_segment(self, _session_id: str, segment: Segment) -> None:
        self.window.add_segment(segment)

    async def get_window(self, _session_id: str) -> ContextWindow:
        return self.window

    async def update_segment(self, _session_id: str, segment: Segment) -> None:
        self.window.update_segment(segment)

    async def save_audio_chunk(
        self,
        _session_id: str,
        segment_id: str,
        audio_data: bytes,
    ) -> None:
        self.saved_audio[segment_id] = audio_data

    async def get_audio_chunk(self, _session_id: str, segment_id: str) -> bytes | None:
        return self.saved_audio.get(segment_id)

    async def update_source_text(
        self,
        _session_id: str,
        segment_id: str,
        new_text: str,
    ) -> None:
        segment = self.window.get_by_id(segment_id)
        if segment:
            segment.text_asr = new_text

    async def update_translation(
        self,
        _session_id: str,
        segment_id: str,
        new_text: str,
    ) -> None:
        segment = self.window.get_by_id(segment_id)
        if segment:
            segment.text_translated = new_text
            segment.status = "revised"

    async def close_session(self, session_id: str) -> None:
        self.closed_sessions.append(session_id)


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.original_audio_queue_max_chunks = settings.audio_queue_max_chunks
        self.original_revision_enabled = settings.revision_enabled
        self.original_diagnostics_emit_interval_seconds = (
            settings.diagnostics_emit_interval_seconds
        )
        settings.revision_enabled = False

    def tearDown(self) -> None:
        settings.audio_queue_max_chunks = self.original_audio_queue_max_chunks
        settings.revision_enabled = self.original_revision_enabled
        settings.diagnostics_emit_interval_seconds = (
            self.original_diagnostics_emit_interval_seconds
        )

    async def test_audio_queue_overflow_emits_status_and_diagnostics(self) -> None:
        settings.audio_queue_max_chunks = 1
        messages: list[dict] = []
        asr = FakeASRService()
        ctx = FakeContextManager()
        pipeline = Pipeline(
            session_id="queue-test",
            asr=asr,
            nmt=FakeNMTService(["unused"]),
            ctx_manager=ctx,
            revision=None,
        )
        pipeline.set_on_message(collect_messages(messages))

        await pipeline.start()
        await pipeline.process_audio(b"first")
        await pipeline.process_audio(b"second")

        status_codes = [
            message.get("code")
            for message in messages
            if message.get("type") == "status"
        ]
        diagnostics = latest_diagnostics(messages)

        self.assertIn("AUDIO_QUEUE_FULL", status_codes)
        self.assertEqual(diagnostics["audio_chunks_received"], 2)
        self.assertEqual(diagnostics["audio_bytes_received"], 11)
        self.assertEqual(diagnostics["audio_chunks_dropped"], 1)
        self.assertEqual(diagnostics["audio_queue_depth"], 1)
        self.assertEqual(diagnostics["audio_queue_max_depth"], 1)
        self.assertEqual(diagnostics["audio_queue_capacity"], 1)

        await pipeline.stop()
        self.assertEqual(asr.reset_calls, 1)
        self.assertEqual(ctx.closed_sessions, ["queue-test"])

    async def test_stop_persists_session_quality(self) -> None:
        """阶段 10 可观测性补全：Pipeline 停止时把质量指标写入会话台账。"""
        import tempfile
        from pathlib import Path

        from services.session_data_service import (
            SessionDataService,
            set_session_data_service,
        )

        tmpdir = tempfile.TemporaryDirectory()
        service = SessionDataService(
            storage_path=Path(tmpdir.name) / "session-history.json",
        )
        set_session_data_service(service)
        try:
            messages: list[dict] = []
            asr = FakeASRService(final_text="Hello world", confidence=0.95)
            ctx = FakeContextManager()
            pipeline = Pipeline(
                session_id="quality-test",
                asr=asr,
                nmt=FakeNMTService(["unused"]),
                ctx_manager=ctx,
                revision=None,
            )
            pipeline.set_on_message(collect_messages(messages))

            await pipeline.start()
            await pipeline.process_audio(b"pcm-audio")
            await asr.wait_until_processed(1)
            await pipeline.wait_for_pending_translations()
            await pipeline.stop()

            sessions = service.list_sessions()
            self.assertEqual(len(sessions), 1)
            record = sessions[0]
            self.assertEqual(record["session_id"], "quality-test")
            self.assertIn("quality", record)
            quality = record["quality"]
            self.assertEqual(quality["asr_segments"], 1)
            self.assertGreaterEqual(record["segment_count"], 0)
        finally:
            set_session_data_service(None)
            tmpdir.cleanup()

    async def test_periodic_diagnostics_emit_audio_counts_without_asr_final(self) -> None:
        settings.diagnostics_emit_interval_seconds = 0
        messages: list[dict] = []
        pipeline = Pipeline(
            session_id="diagnostics-test",
            asr=FakeASRService(),
            nmt=FakeNMTService(["unused"]),
            ctx_manager=FakeContextManager(),
            revision=None,
        )
        pipeline.set_on_message(collect_messages(messages))

        await pipeline.start()
        await pipeline.process_audio(b"pcm-audio")

        diagnostics = latest_diagnostics(messages)
        self.assertEqual(diagnostics["audio_chunks_received"], 1)
        self.assertEqual(diagnostics["audio_bytes_received"], 9)
        self.assertEqual(diagnostics["audio_chunks_dropped"], 0)

        await pipeline.stop()

    async def test_final_asr_segment_translates_and_updates_diagnostics(self) -> None:
        settings.audio_queue_max_chunks = 4
        processed_event = asyncio.Event()
        messages: list[dict] = []
        asr = FakeASRService(
            final_text="hello world",
            confidence=0.91,
            processed_event=processed_event,
        )
        nmt = FakeNMTService(["ni ", "hao"])
        ctx = FakeContextManager()
        pipeline = Pipeline(
            session_id="flow-test",
            asr=asr,
            nmt=nmt,
            ctx_manager=ctx,
            revision=None,
        )
        pipeline.set_on_message(collect_messages(messages))

        await pipeline.start()
        await pipeline.process_audio(b"pcm-audio")
        await asyncio.wait_for(processed_event.wait(), timeout=1)
        # 翻译已异步化：显式等待在途翻译任务，避免时序竞争
        await pipeline.wait_for_pending_translations(timeout=1)

        segment = ctx.window.get_by_id("flow-test_0")
        self.assertIsNotNone(segment)
        if segment is None:
            raise AssertionError("Expected segment flow-test_0")

        self.assertEqual(segment.text_asr, "hello world")
        self.assertEqual(segment.text_translated, "ni hao")
        self.assertEqual(segment.status, "final")
        self.assertEqual(ctx.saved_audio["flow-test_0"], b"pcm-audio")
        self.assertEqual(nmt.translation_calls, 1)

        translation_tokens = [
            message
            for message in messages
            if message.get("type") == "translation_token"
        ]
        self.assertEqual(
            [message.get("token") for message in translation_tokens],
            ["ni ", "hao", ""],
        )
        self.assertEqual(
            [message.get("is_final") for message in translation_tokens],
            [False, False, True],
        )

        diagnostics = latest_diagnostics(messages)
        self.assertEqual(diagnostics["asr_segments"], 1)
        self.assertEqual(diagnostics["translation_segments"], 1)
        self.assertEqual(diagnostics["api_call_counts"]["nmt_stream"], 1)
        self.assertEqual(diagnostics["audio_chunks_received"], 1)
        self.assertEqual(diagnostics["audio_chunks_dropped"], 0)
        self.assertEqual(diagnostics["latency"]["audio_queue_wait_ms"]["count"], 1)
        self.assertEqual(diagnostics["latency"]["capture_to_asr_ms"]["count"], 1)
        self.assertEqual(diagnostics["latency"]["asr_to_first_token_ms"]["count"], 1)
        self.assertEqual(
            diagnostics["latency"]["asr_to_translation_final_ms"]["count"],
            1,
        )

        message_count_before_stop = len(messages)
        await pipeline.stop()
        await pipeline.process_audio(b"ignored")

        self.assertEqual(asr.reset_calls, 1)
        self.assertEqual(ctx.closed_sessions, ["flow-test"])
        self.assertEqual(len(messages), message_count_before_stop + 1)
        self.assertEqual(latest_diagnostics(messages)["status"], "closed")

    async def test_config_update_applies_language_to_future_segments(self) -> None:
        processed_event = asyncio.Event()
        messages: list[dict] = []
        asr = FakeASRService(
            final_text="bonjour",
            confidence=0.91,
            processed_event=processed_event,
        )
        nmt = FakeNMTService(["ni hao"])
        ctx = FakeContextManager()
        pipeline = Pipeline(
            session_id="language-test",
            asr=asr,
            nmt=nmt,
            ctx_manager=ctx,
            revision=None,
        )
        pipeline.set_on_message(collect_messages(messages))

        await pipeline.start()
        await pipeline.update_config(language="fr", target_language="zh-CN")
        await pipeline.process_audio(b"pcm-audio")
        await asyncio.wait_for(processed_event.wait(), timeout=1)

        segment = ctx.window.get_by_id("language-test_0")
        self.assertIsNotNone(segment)
        if segment is None:
            raise AssertionError("Expected segment language-test_0")

        self.assertEqual(asr.language_updates[-1], "fr")
        self.assertEqual(segment.source_language, "fr")
        self.assertEqual(segment.target_language, "zh-CN")
        self.assertEqual(nmt.segments[0].source_language, "fr")
        self.assertEqual(nmt.segments[0].target_language, "zh-CN")

        status_messages = [
            message
            for message in messages
            if message.get("type") == "status"
        ]
        self.assertTrue(
            any(message.get("code") == "CONFIG_UPDATED" for message in status_messages),
        )

        await pipeline.stop()

    async def test_auto_source_language_detection_updates_segments(self) -> None:
        """阶段 8：auto 模式下 Whisper 检测语言应更新会话源语言。"""
        processed_event = asyncio.Event()
        messages: list[dict] = []
        asr = FakeASRService(
            final_text="こんにちは",
            confidence=0.9,
            processed_event=processed_event,
            detected_language="japanese",
        )
        nmt = FakeNMTService(["你好"])
        ctx = FakeContextManager()
        pipeline = Pipeline(
            session_id="auto-lang-test",
            asr=asr,
            nmt=nmt,
            ctx_manager=ctx,
            revision=None,
        )
        pipeline.set_on_message(collect_messages(messages))
        # 初始为 auto
        await pipeline.update_config(language="auto", target_language="zh-CN")

        await pipeline.start()
        await pipeline.process_audio(b"pcm-audio")
        await asyncio.wait_for(processed_event.wait(), timeout=1)

        segment = ctx.window.get_by_id("auto-lang-test_0")
        self.assertIsNotNone(segment)
        if segment is None:
            raise AssertionError("Expected segment auto-lang-test_0")

        # 检测到日语后，会话源语言应更新为 ja
        self.assertEqual(segment.source_language, "ja")
        self.assertEqual(segment.target_language, "zh-CN")
        self.assertEqual(asr.language_updates[-1], "ja")
        self.assertEqual(nmt.segments[0].source_language, "ja")

        # asr_final 消息应携带 detected_language
        asr_final_messages = [
            message
            for message in messages
            if message.get("type") == "asr_final"
        ]
        self.assertTrue(asr_final_messages)
        self.assertEqual(asr_final_messages[0].get("detected_language"), "ja")

        await pipeline.stop()

    async def test_non_auto_source_language_keeps_detected_language_absent(self) -> None:
        """非 auto 模式不应用自动检测，detected_language 保持 None。"""
        processed_event = asyncio.Event()
        messages: list[dict] = []
        asr = FakeASRService(
            final_text="hello",
            confidence=0.9,
            processed_event=processed_event,
            detected_language="english",
        )
        nmt = FakeNMTService(["你好"])
        ctx = FakeContextManager()
        pipeline = Pipeline(
            session_id="fixed-lang-test",
            asr=asr,
            nmt=nmt,
            ctx_manager=ctx,
            revision=None,
        )
        pipeline.set_on_message(collect_messages(messages))
        # 显式指定 en（非 auto）
        await pipeline.update_config(language="en", target_language="zh-CN")

        await pipeline.start()
        await pipeline.process_audio(b"pcm-audio")
        await asyncio.wait_for(processed_event.wait(), timeout=1)

        segment = ctx.window.get_by_id("fixed-lang-test_0")
        self.assertIsNotNone(segment)
        if segment is None:
            raise AssertionError("Expected segment fixed-lang-test_0")

        self.assertEqual(segment.source_language, "en")
        # 非 auto 模式即使 ASR 返回检测语言也不应用
        asr_final_messages = [
            message
            for message in messages
            if message.get("type") == "asr_final"
        ]
        self.assertTrue(asr_final_messages)
        self.assertIsNone(asr_final_messages[0].get("detected_language"))

        await pipeline.stop()


class PipelineAsyncTests(unittest.IsolatedAsyncioTestCase):
    """验证翻译异步化：ASR 回调不再阻塞下一句的处理。"""

    def setUp(self) -> None:
        self.original_revision_enabled = settings.revision_enabled
        settings.revision_enabled = False

    def tearDown(self) -> None:
        settings.revision_enabled = self.original_revision_enabled

    async def test_asr_callback_does_not_block_next_sentence(self) -> None:
        release = asyncio.Event()
        messages: list[dict] = []
        asr = FakeASRService(final_text="hello", confidence=0.9)
        nmt = BlockingNMTService(["译"], release)
        pipeline = Pipeline(
            session_id="async-test",
            asr=asr,
            nmt=nmt,
            ctx_manager=FakeContextManager(),
            revision=None,
        )
        pipeline.set_on_message(collect_messages(messages))

        await pipeline.start()
        await pipeline.process_audio(b"pcm-1")
        await pipeline.process_audio(b"pcm-2")
        await asr.wait_until_processed(2)

        # 第二句的 ASR 结果应已发出，而第一句翻译仍在阻塞 —— 证明未阻塞
        asr_final_events = [
            message
            for message in messages
            if message.get("type") == "asr_final"
        ]
        self.assertGreaterEqual(len(asr_final_events), 2)
        self.assertEqual(
            [message.get("segment_index") for message in asr_final_events],
            [0, 1],
        )

        release.set()
        await pipeline.wait_for_pending_translations(timeout=1)
        await pipeline.stop()

    async def test_out_of_order_translation_results_carry_index(self) -> None:
        original_max_concurrent = settings.max_concurrent_translations
        settings.max_concurrent_translations = 10
        try:
            await self._run_out_of_order_scenario()
        finally:
            settings.max_concurrent_translations = original_max_concurrent

    async def _run_out_of_order_scenario(self) -> None:
        release = asyncio.Event()
        messages: list[dict] = []

        # 慢翻译（第一句）+ 快翻译（第三句）：让第三句先完成
        slow_nmt = BlockingNMTService(["慢"], release)
        fast_nmt = FakeNMTService(["快"])

        asr = FakeASRService(final_text="sentence", confidence=0.9)
        ctx = FakeContextManager()

        pipeline = Pipeline(
            session_id="order-test",
            asr=asr,
            nmt=slow_nmt,
            ctx_manager=ctx,
            revision=None,
        )
        pipeline.set_on_message(collect_messages(messages))

        await pipeline.start()
        await pipeline.process_audio(b"pcm-1")  # 触发第一句（慢翻译）
        await pipeline.process_audio(b"pcm-2")  # 触发第二句（慢翻译）
        await asr.wait_until_processed(2)

        # 等两个慢翻译任务真正进入 translate_stream 并被 release 阻塞
        deadline = asyncio.get_running_loop().time() + 1.0
        while slow_nmt.translation_calls < 2:
            if asyncio.get_running_loop().time() >= deadline:
                raise AssertionError("Slow translations did not start in time")
            await asyncio.sleep(0.01)

        # 慢翻译任务已阻塞：替换为快翻译处理第三句
        pipeline._nmt = fast_nmt
        await pipeline.process_audio(b"pcm-3")  # 触发第三句（快翻译）
        await asr.wait_until_processed(3)

        # 快翻译先完成，其 translation_token 带正确的 segment_index
        fast_final = [
            message
            for message in messages
            if message.get("type") == "translation_token"
            and message.get("is_final") is True
        ]
        self.assertTrue(fast_final)
        self.assertEqual(fast_final[0].get("segment_index"), 2)

        release.set()
        await pipeline.wait_for_pending_translations(timeout=1)
        await pipeline.stop()

    async def test_tts_audio_emitted_after_final_translation(self) -> None:
        """译文 final 后，若配置了 TTS 服务，应下发 tts_audio 元信息帧 + 二进制音频帧。"""
        original_engine = settings.tts_engine
        settings.tts_engine = "off"
        try:
            messages: list[dict] = []
            byte_frames: list[bytes] = []

            class FakeTTSService:
                enabled = True

                async def synthesize(self, text: str, language: str = "zh-CN") -> bytes:
                    return f"mp3:{text}:{language}".encode("utf-8")

            processed_event = asyncio.Event()
            asr = FakeASRService(
                final_text="hello tts",
                confidence=0.9,
                processed_event=processed_event,
            )
            pipeline = Pipeline(
                session_id="tts-test",
                asr=asr,
                nmt=FakeNMTService(["你好 tts"]),
                ctx_manager=FakeContextManager(),
                revision=None,
                tts=FakeTTSService(),
            )
            pipeline.set_on_message(collect_messages(messages))

            async def collect_bytes(payload: bytes) -> None:
                byte_frames.append(payload)

            pipeline.set_on_message_bytes(collect_bytes)

            await pipeline.start()
            await pipeline.process_audio(b"pcm-audio")
            await asyncio.wait_for(processed_event.wait(), timeout=1)
            await pipeline.wait_for_pending_translations(timeout=1)

            tts_meta = [
                message
                for message in messages
                if message.get("type") == "tts_audio"
            ]
            self.assertEqual(len(tts_meta), 1)
            self.assertEqual(tts_meta[0]["segment_id"], "tts-test_0")
            self.assertEqual(tts_meta[0]["format"], "mp3")
            self.assertGreater(tts_meta[0]["length"], 0)
            self.assertEqual(byte_frames, ["mp3:".encode() + "你好 tts:zh-CN".encode("utf-8")])

            await pipeline.stop()
        finally:
            settings.tts_engine = original_engine

    async def test_tts_disabled_skips_audio(self) -> None:
        """tts_engine=off 时不触发合成，也不下发 tts_audio。"""
        original_engine = settings.tts_engine
        settings.tts_engine = "off"
        try:
            messages: list[dict] = []
            processed_event = asyncio.Event()
            asr = FakeASRService(
                final_text="hello",
                confidence=0.9,
                processed_event=processed_event,
            )
            pipeline = Pipeline(
                session_id="tts-off-test",
                asr=asr,
                nmt=FakeNMTService(["你好"]),
                ctx_manager=FakeContextManager(),
                revision=None,
                tts=None,
            )
            pipeline.set_on_message(collect_messages(messages))

            await pipeline.start()
            await pipeline.process_audio(b"pcm-audio")
            await asyncio.wait_for(processed_event.wait(), timeout=1)
            await pipeline.wait_for_pending_translations(timeout=1)

            tts_meta = [
                message
                for message in messages
                if message.get("type") == "tts_audio"
            ]
            self.assertEqual(tts_meta, [])

            await pipeline.stop()
        finally:
            settings.tts_engine = original_engine

    async def test_update_glossary_injects_hotwords_to_asr(self) -> None:
        """阶段 2：更新术语表时，术语 source 应同步注入 ASR 热词。"""
        processed_event = asyncio.Event()
        messages: list[dict] = []
        asr = FakeASRService(
            final_text="kubernetes is hard",
            confidence=0.9,
            processed_event=processed_event,
        )
        pipeline = Pipeline(
            session_id="hotwords-test",
            asr=asr,
            nmt=FakeNMTService(["你好"]),
            ctx_manager=FakeContextManager(),
            revision=None,
        )
        pipeline.set_on_message(collect_messages(messages))

        await pipeline.start()
        await pipeline.update_glossary([
            {"source": "Kubernetes", "target": "容器编排平台"},
            {"source": "K8s", "target": "Kubernetes"},
            {"source": "Transformer", "target": "变换器", "keep_original": True},
        ])

        self.assertEqual(asr.hotword_updates, [["Kubernetes", "K8s", "Transformer"]])

        status_messages = [
            message for message in messages if message.get("type") == "status"
        ]
        updated = [
            message for message in status_messages
            if message.get("code") == "GLOSSARY_UPDATED"
        ]
        self.assertEqual(len(updated), 1)
        self.assertEqual(updated[0]["asr_hotwords"], 3)

        await pipeline.stop()

    async def test_config_toggles_asr_hotwords(self) -> None:
        """阶段 2：config 消息可运行时开关 ASR 热词注入。"""
        processed_event = asyncio.Event()
        asr = FakeASRService(
            final_text="hello",
            confidence=0.9,
            processed_event=processed_event,
        )
        pipeline = Pipeline(
            session_id="hotwords-toggle",
            asr=asr,
            nmt=FakeNMTService(["你好"]),
            ctx_manager=FakeContextManager(),
            revision=None,
        )

        await pipeline.start()
        await pipeline.update_config(asr_hotwords_enabled=False)
        self.assertFalse(asr.hotwords_enabled)

        await pipeline.update_config(asr_hotwords_enabled=True)
        self.assertTrue(asr.hotwords_enabled)

        await pipeline.stop()


def collect_messages(messages: list[dict]) -> Callable[[dict], Awaitable[None]]:
    async def collect(message: dict) -> None:
        messages.append(message)

    return collect


class RecordingRevisionService:
    """模拟修正引擎：返回一条已修正的译文。"""

    def __init__(self, corrected_translation: str, source_text: str | None = None) -> None:
        self.corrected_translation = corrected_translation
        self.source_text = source_text
        self.calls = 0

    async def check_asr_correction(self, *args, **kwargs):
        from services.revision_service import RevisionResult

        self.calls += 1
        return RevisionResult(
            segment_id="seg_0",
            new_text=self.corrected_translation,
            reason="asr_correction",
            source_text=self.source_text or "corrected source",
            old_text="old translation",
            old_source_text="original source",
            correction_source="audio_redecode",
            trigger="low_confidence",
        )

    async def check_and_revise(self, *args, **kwargs):
        return []

    def consume_api_call_counts(self):
        return {}

    def consume_skipped_counts(self):
        return {}

    def has_semantic_ambiguity(self, segment):
        return False

    @property
    def total_revisions(self):
        return 0


class PipelineTests_TMRevision(unittest.IsolatedAsyncioTestCase):
    """修正后译文写回翻译记忆库（越用越准）的验证。"""

    def setUp(self) -> None:
        self.original_revision_enabled = settings.revision_enabled
        settings.revision_enabled = True

    def tearDown(self) -> None:
        settings.revision_enabled = self.original_revision_enabled

    async def test_asr_revision_writes_corrected_translation_to_tm(self) -> None:
        messages: list[dict] = []
        asr = FakeASRService(final_text="hello world", confidence=0.30)
        ctx = FakeContextManager()
        nmt = FakeNMTService([""])
        revision = RecordingRevisionService(
            corrected_translation="修正后的译文",
            source_text="corrected source text",
        )
        pipeline = Pipeline(
            session_id="tm-rev-test",
            asr=asr,
            nmt=nmt,
            ctx_manager=ctx,
            revision=revision,
        )
        pipeline.set_on_message(collect_messages(messages))

        # 预置一个已翻译的片段，作为修正目标
        ctx.window = ContextWindow(session_id="tm-rev-test", window_size=10)
        seg = Segment(
            id="tm-rev-test_0",
            text_asr="original source",
            text_translated="old translation",
            confidence=0.30,
            status="final",
        )
        ctx.window.add_segment(seg)

        # 单独调用修正写回逻辑
        await pipeline.start()
        await pipeline._run_revision(seg)
        await pipeline.stop()

        tm = pipeline._translation_memory
        self.assertIsNotNone(tm)
        match = tm.lookup("corrected source text")
        self.assertIsNotNone(match)
        self.assertEqual(match.translated, "修正后的译文")

    async def test_periodic_revision_writes_corrected_translation_to_tm(self) -> None:
        messages: list[dict] = []
        asr = FakeASRService(final_text="hello world", confidence=0.30)
        ctx = FakeContextManager()
        nmt = FakeNMTService([""])

        class ReviseOnce:
            """check_and_revise 返回一条修正。"""

            def __init__(self):
                self.revision_calls = 0

            async def check_asr_correction(self, *args, **kwargs):
                return None

            async def check_and_revise(self, *args, **kwargs):
                from services.revision_service import RevisionResult

                self.revision_calls += 1
                if self.revision_calls == 1:
                    return [RevisionResult(
                        segment_id="tm-rev-test_0",
                        new_text="润色后的译文",
                        reason="translation_correction",
                        source_text=None,
                        old_text="old translation",
                        old_source_text="original source",
                        correction_source="translation_window",
                        trigger="sentence_count",
                    )]
                return []

            def consume_api_call_counts(self):
                return {}

            def consume_skipped_counts(self):
                return {}

            def has_semantic_ambiguity(self, segment):
                return False

            @property
            def total_revisions(self):
                return 0

        revision = ReviseOnce()
        pipeline = Pipeline(
            session_id="tm-rev-test",
            asr=asr,
            nmt=nmt,
            ctx_manager=ctx,
            revision=revision,
        )
        pipeline.set_on_message(collect_messages(messages))

        ctx.window = ContextWindow(session_id="tm-rev-test", window_size=10)
        # 需要至少两个片段，最后一个为当前正在处理的片段，
        # 前面一个进入可修正窗口（revisable = segments[-max_window:-1]）。
        seg_old = Segment(
            id="tm-rev-test_0",
            text_asr="original source",
            text_translated="old translation",
            confidence=0.30,
            status="final",
        )
        seg = Segment(
            id="tm-rev-test_1",
            text_asr="current sentence",
            text_translated="current translation",
            confidence=0.95,
            status="final",
        )
        ctx.window.add_segment(seg_old)
        ctx.window.add_segment(seg)

        await pipeline.start()
        # 使 _check_revision 的句数触发条件满足
        pipeline._sentence_count = settings.revision_trigger_sentences
        await pipeline._run_revision(seg)
        await pipeline.stop()

        tm = pipeline._translation_memory
        # 润色修正后应写回：用旧源句查，命中且为润色后译文
        match = tm.lookup("original source")
        self.assertIsNotNone(match)
        self.assertEqual(match.translated, "润色后的译文")


def latest_diagnostics(messages: list[dict]) -> dict:
    for message in reversed(messages):
        if message.get("type") != "session_diagnostics":
            continue

        diagnostics = message.get("diagnostics")
        if isinstance(diagnostics, dict):
            return diagnostics

    raise AssertionError("Expected a session diagnostics message.")


if __name__ == "__main__":
    unittest.main()
