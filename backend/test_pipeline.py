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


FinalCallback = Callable[[str, float], Awaitable[None]]
PartialCallback = Callable[[str], Awaitable[None]]


class FakeASRService:
    def __init__(
        self,
        *,
        final_text: str | None = None,
        confidence: float = 0.9,
        processed_event: asyncio.Event | None = None,
    ) -> None:
        self.final_text = final_text
        self.confidence = confidence
        self.processed_event = processed_event
        self.processed_chunks: list[bytes] = []
        self.reset_calls = 0
        self.language_updates: list[str] = []
        self._on_partial: Optional[PartialCallback] = None
        self._on_final: Optional[FinalCallback] = None
        self._last_audio_chunk = b""

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

    async def process_chunk(self, audio_bytes: bytes) -> int:
        self.processed_chunks.append(audio_bytes)
        self._last_audio_chunk = audio_bytes

        emitted = 0
        if self.final_text and self._on_final:
            await self._on_final(self.final_text, self.confidence)
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

    async def translate_stream(self, context: ContextWindow, current: Segment):
        self.translation_calls += 1
        self.segments.append(current)
        self.last_context = context

        for token in self.tokens:
            yield token
        yield "<FINAL>"


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


def collect_messages(messages: list[dict]) -> Callable[[dict], Awaitable[None]]:
    async def collect(message: dict) -> None:
        messages.append(message)

    return collect


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
