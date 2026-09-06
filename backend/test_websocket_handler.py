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
        self.style_presets: list[object] = []
        self.manual_revision_calls = 0
        self.diagnostics_calls = 0
        self.nmt_style_preset = "concise"
        self.hotwords_toggles: list[bool] = []

    async def update_config(
        self,
        *,
        language: object | None = None,
        target_language: object | None = None,
        style_preset: object | None = None,
        asr_hotwords_enabled: object | None = None,
    ) -> None:
        self.config_updates.append((language, target_language))
        if style_preset is not None:
            self.style_presets.append(style_preset)
            self.nmt_style_preset = str(style_preset)
        if asr_hotwords_enabled is not None:
            self.hotwords_toggles.append(bool(asr_hotwords_enabled))
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

    async def test_config_message_forwards_style_preset(self) -> None:
        """阶段 3：config 控制消息应透传 style_preset 到 pipeline。"""
        handler = WebSocketHandler()
        pipeline = FakePipeline()

        await handler._handle_control_message(
            pipeline,
            '{"type":"config","language":"en","target_language":"zh-CN","style_preset":"lecture"}',
        )

        self.assertEqual(pipeline.style_presets, ["lecture"])
        self.assertEqual(pipeline.nmt_style_preset, "lecture")
        self.assertEqual(pipeline.language_config.source_language, "en")

    async def test_config_message_without_style_preset_keeps_current(self) -> None:
        """不带 style_preset 的 config 消息不应覆盖现有风格。"""
        handler = WebSocketHandler()
        pipeline = FakePipeline()

        await handler._handle_control_message(
            pipeline,
            '{"type":"config","language":"fr","target_language":"zh-CN"}',
        )

        self.assertEqual(pipeline.style_presets, [])
        self.assertEqual(pipeline.nmt_style_preset, "concise")

    async def test_config_message_forwards_asr_hotwords_toggle(self) -> None:
        """阶段 2：config 消息应透传 asr_hotwords_enabled 开关。"""
        handler = WebSocketHandler()
        pipeline = FakePipeline()

        await handler._handle_control_message(
            pipeline,
            '{"type":"config","asr_hotwords_enabled":false}',
        )

        self.assertEqual(pipeline.hotwords_toggles, [False])

        await handler._handle_control_message(
            pipeline,
            '{"type":"config","asr_hotwords_enabled":true}',
        )
        self.assertEqual(pipeline.hotwords_toggles, [False, True])

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

    async def test_translation_memory_summary_aggregates_active_sessions(self) -> None:
        """V5.3：聚合所有活跃会话的翻译记忆库统计。"""
        from core.config import settings
        from core.pipeline import Pipeline
        from services.asr_service import ASRService
        from services.context_manager import ContextManager
        from services.nmt_service import NMTService

        handler = WebSocketHandler()

        pipeline_a = Pipeline(
            session_id="session-a",
            asr=ASRService(),
            nmt=NMTService(),
            ctx_manager=ContextManager(),
        )
        pipeline_b = Pipeline(
            session_id="session-b",
            asr=ASRService(),
            nmt=NMTService(),
            ctx_manager=ContextManager(),
        )
        # 每个会话写一条记忆
        pipeline_a._translation_memory.add(
            "Hello world", "你好世界", language_pair="en->zh-CN",
        )
        pipeline_b._translation_memory.add(
            "Good morning", "早上好", language_pair="en->zh-CN",
        )
        handler._active_pipelines["session-a"] = pipeline_a
        handler._active_pipelines["session-b"] = pipeline_b

        summary = handler.translation_memory_summary()

        self.assertEqual(summary["size"], 2)
        self.assertEqual(summary["written"], 2)
        self.assertEqual(len(summary["sessions"]), 2)
        self.assertEqual(summary["threshold"], settings.translation_memory_threshold)

    async def test_clear_translation_memory_clears_active_sessions(self) -> None:
        """V5.3：清空所有活跃会话的记忆库。"""
        from core.pipeline import Pipeline
        from services.asr_service import ASRService
        from services.context_manager import ContextManager
        from services.nmt_service import NMTService

        handler = WebSocketHandler()
        pipeline = Pipeline(
            session_id="session-c",
            asr=ASRService(),
            nmt=NMTService(),
            ctx_manager=ContextManager(),
        )
        pipeline._translation_memory.add(
            "Hello world", "你好世界", language_pair="en->zh-CN",
        )
        handler._active_pipelines["session-c"] = pipeline

        cleared = handler.clear_translation_memory()

        self.assertEqual(cleared, 1)
        self.assertEqual(pipeline.translation_memory_stats()["size"], 0)


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
