from __future__ import annotations

from pathlib import Path
import sys
import unittest


BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from api.websocket_handler import ChunkRateLimiter, WebSocketHandler
from services.language_config import LanguageConfig


class FakePipeline:
    def __init__(self) -> None:
        self.session_id = "config-test"
        self.language_config = LanguageConfig()
        self.config_updates: list[tuple[object, object]] = []
        self.manual_revision_calls = 0
        self.diagnostics_calls = 0

    async def update_config(
        self,
        *,
        language: object | None = None,
        target_language: object | None = None,
    ) -> None:
        self.config_updates.append((language, target_language))
        self.language_config = LanguageConfig.from_values(language, target_language)

    async def trigger_manual_revision(self) -> None:
        self.manual_revision_calls += 1

    async def emit_diagnostics(self) -> None:
        self.diagnostics_calls += 1


class WebSocketHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_config_message_updates_pipeline_language_pair(self) -> None:
        handler = WebSocketHandler()
        pipeline = FakePipeline()

        await handler._handle_control_message(
            pipeline,
            '{"type":"config","language":"ja","target_language":"zh-CN"}',
        )

        self.assertEqual(pipeline.config_updates, [("ja", "zh-CN")])
        self.assertEqual(pipeline.language_config.source_language, "ja")
        self.assertEqual(pipeline.language_config.target_language, "zh-CN")

    async def test_manual_revision_message_still_routes_to_pipeline(self) -> None:
        handler = WebSocketHandler()
        pipeline = FakePipeline()

        await handler._handle_control_message(pipeline, '{"type":"manual_revise"}')

        self.assertEqual(pipeline.manual_revision_calls, 1)

    async def test_request_diagnostics_message_routes_to_pipeline(self) -> None:
        handler = WebSocketHandler()
        pipeline = FakePipeline()

        await handler._handle_control_message(pipeline, '{"type":"request_diagnostics"}')

        self.assertEqual(pipeline.diagnostics_calls, 1)

    async def test_reconnect_token_roundtrip(self) -> None:
        handler = WebSocketHandler()

        token = handler.issue_reconnect_token("session-a")
        self.assertGreater(len(token), 20)
        self.assertTrue(handler.verify_reconnect_token("session-a", token))
        self.assertFalse(handler.verify_reconnect_token("session-a", "forged-token"))
        self.assertFalse(handler.verify_reconnect_token("session-b", token))

    async def test_has_active_pipeline_tracks_connected_sessions(self) -> None:
        handler = WebSocketHandler()

        self.assertFalse(handler.has_active_pipeline("session-x"))

        from core.pipeline import Pipeline
        from services.asr_service import ASRService
        from services.context_manager import ContextManager
        from services.nmt_service import NMTService

        pipeline = Pipeline(
            session_id="session-x",
            asr=ASRService(),
            nmt=NMTService(),
            ctx_manager=ContextManager(),
        )
        handler._active_pipelines["session-x"] = pipeline
        self.assertTrue(handler.has_active_pipeline("session-x"))


class ChunkRateLimiterTests(unittest.IsolatedAsyncioTestCase):
    def test_allows_up_to_max_frames_per_second(self) -> None:
        limiter = ChunkRateLimiter(max_per_second=3)

        self.assertTrue(limiter.allow(100.0))
        self.assertTrue(limiter.allow(100.2))
        self.assertTrue(limiter.allow(100.4))
        self.assertFalse(limiter.allow(100.6))  # 第 4 帧超限

    def test_window_slides_after_one_second(self) -> None:
        limiter = ChunkRateLimiter(max_per_second=3)
        for index in range(3):
            self.assertTrue(limiter.allow(200.0 + index * 0.1))

        # 第 3 帧时间戳已滑出 1 秒窗口
        self.assertTrue(limiter.allow(201.5))


if __name__ == "__main__":
    unittest.main()
