from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.tts_service import TTSService  # noqa: E402


def run(coro) -> None:
    """Run an async test body synchronously."""
    return asyncio.run(coro)


class TTSServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        # 默认 engine=off + 禁用磁盘缓存，确保单测不发起网络/合成调用、不依赖磁盘状态。
        engine_patcher = patch("core.config.settings.tts_engine", "off")
        engine_patcher.start()
        self.addCleanup(engine_patcher.stop)
        cache_dir_patcher = patch("core.config.settings.tts_cache_dir", "")
        cache_dir_patcher.start()
        self.addCleanup(cache_dir_patcher.stop)
        self.service = TTSService()

    def test_disabled_engine_returns_empty(self) -> None:
        async def scenario() -> None:
            self.assertFalse(self.service.enabled)
            audio = await self.service.synthesize("你好世界", language="zh-CN")
            self.assertEqual(audio, b"")

        run(scenario())

    def test_disabled_engine_diagnostics(self) -> None:
        diag = self.service.diagnostics
        self.assertEqual(diag["engine"], "off")
        self.assertFalse(diag["enabled"])
        self.assertEqual(diag["synthesized"], 0)
        self.assertEqual(diag["failed"], 0)

    def test_blank_text_returns_empty(self) -> None:
        with patch("core.config.settings.tts_engine", "edge"):
            service = TTSService()

            async def scenario() -> None:
                audio = await service.synthesize("   ", language="zh-CN")
                self.assertEqual(audio, b"")

            run(scenario())

    def test_edge_synthesis_caches_and_counts(self) -> None:
        fake_mp3 = b"\x49\x44\x33fake-mp3-bytes"
        with (
            patch("core.config.settings.tts_engine", "edge"),
            patch.object(
                TTSService, "_synthesize_edge", return_value=fake_mp3
            ) as mock_edge,
        ):
            service = TTSService()

            async def scenario() -> None:
                first = await service.synthesize("你好世界", language="zh-CN")
                second = await service.synthesize("你好世界", language="zh-CN")

                self.assertEqual(first, fake_mp3)
                self.assertEqual(second, fake_mp3)
                # 第二次命中缓存，不再调用底层合成
                self.assertEqual(mock_edge.call_count, 1)

            run(scenario())

    def test_openai_engine_uses_httpx(self) -> None:
        fake_mp3 = b"openai-mp3"
        with (
            patch("core.config.settings.tts_engine", "openai"),
            patch(
                "core.config.settings.tts_openai_api_key", "test-key"
            ),
            patch.object(TTSService, "_synthesize_openai", return_value=fake_mp3),
        ):
            service = TTSService()

            async def scenario() -> None:
                audio = await service.synthesize("hello", language="en")
                self.assertEqual(audio, fake_mp3)

            run(scenario())

    def test_synthesis_failure_returns_empty_and_counts(self) -> None:
        with (
            patch("core.config.settings.tts_engine", "edge"),
            patch.object(
                TTSService, "_synthesize_edge", side_effect=RuntimeError("boom")
            ),
        ):
            service = TTSService()

            async def scenario() -> None:
                audio = await service.synthesize("你好", language="zh-CN")
                self.assertEqual(audio, b"")
                self.assertEqual(service.diagnostics["failed"], 1)

            run(scenario())

    def test_clear_cache_resets(self) -> None:
        with patch("core.config.settings.tts_engine", "edge"):
            service = TTSService()
            service._cache["k"] = b"x"
            service._cache_hits = 2
            service._synthesized = 3
            service._failed = 1

            service.clear_cache()

            self.assertEqual(service.diagnostics["cacheSize"], 0)
            self.assertEqual(service.diagnostics["cacheHits"], 0)
            self.assertEqual(service.diagnostics["synthesized"], 0)
            self.assertEqual(service.diagnostics["failed"], 0)

    def test_cache_key_varies_by_voice_and_language(self) -> None:
        with patch("core.config.settings.tts_engine", "edge"):
            service = TTSService()
            key_zh = service._cache_key("你好", "zh-CN")
            key_en = service._cache_key("你好", "en")
            key_diff_voice = service._cache_key("你好", "zh-CN")

            self.assertNotEqual(key_zh, key_en)
            self.assertEqual(key_zh, key_diff_voice)

    def test_update_settings_changes_voice_rate_and_volume_and_clears_cache(self) -> None:
        with patch("core.config.settings.tts_engine", "edge"):
            service = TTSService()
            service._cache["k"] = b"x"
            self.assertEqual(service.voice, "zh-CN-XiaoxiaoNeural")
            self.assertEqual(service.volume, "+0%")

            service.update_settings(
                voice="zh-CN-YunxiNeural", rate="+10%", volume="+25%"
            )

            self.assertEqual(service.voice, "zh-CN-YunxiNeural")
            self.assertEqual(service.rate, "+10%")
            self.assertEqual(service.volume, "+25%")
            # 语音/语速/音量变化应清空缓存，避免旧结果误命中
            self.assertEqual(service.diagnostics["cacheSize"], 0)

    def test_update_settings_volume_change_clears_cache(self) -> None:
        with patch("core.config.settings.tts_engine", "edge"):
            service = TTSService()
            service._cache["k"] = b"x"

            service.update_settings(volume="+50%")

            self.assertEqual(service.volume, "+50%")
            self.assertEqual(service.diagnostics["cacheSize"], 0)

    def test_cache_key_varies_by_volume(self) -> None:
        with patch("core.config.settings.tts_engine", "edge"):
            service = TTSService()
            key_normal = service._cache_key("你好", "zh-CN")
            service.update_settings(volume="+50%")
            key_loud = service._cache_key("你好", "zh-CN")

            self.assertNotEqual(key_normal, key_loud)

    def test_update_settings_noop_keeps_cache(self) -> None:
        with patch("core.config.settings.tts_engine", "edge"):
            service = TTSService()
            service._cache["k"] = b"x"

            service.update_settings(voice=None, rate=None, volume=None)

            # 无变化时不清缓存
            self.assertEqual(service.diagnostics["cacheSize"], 1)

    def test_disk_cache_reads_back_on_second_service(self) -> None:
        """磁盘缓存跨实例复用：第一个服务合成并落盘，第二个服务直接命中磁盘。"""
        fake_mp3 = b"\x49\x44\x33disk-cached-mp3"
        with tempfile.TemporaryDirectory() as cache_dir:
            with (
                patch("core.config.settings.tts_engine", "edge"),
                patch("core.config.settings.tts_cache_dir", cache_dir),
            ):
                service = TTSService()
                self.assertIsNotNone(service._cache_dir)

                with patch.object(
                    TTSService, "_synthesize_edge", return_value=fake_mp3
                ) as mock_edge:
                    run_service_1 = TTSService()
                    async def scenario1() -> None:
                        audio = await run_service_1.synthesize("磁盘缓存", language="zh-CN")
                        self.assertEqual(audio, fake_mp3)
                    run(scenario1())
                    self.assertEqual(mock_edge.call_count, 1)

                # 第二个服务：应从磁盘命中，不再调用底层合成
                with patch.object(
                    TTSService, "_synthesize_edge", return_value=b"should-not-be-used"
                ) as mock_edge2:
                    service2 = TTSService()
                    async def scenario2() -> None:
                        audio = await service2.synthesize("磁盘缓存", language="zh-CN")
                        self.assertEqual(audio, fake_mp3)
                        self.assertEqual(service2.diagnostics["diskHits"], 1)
                    run(scenario2())
                    self.assertEqual(mock_edge2.call_count, 0)

    def test_disk_cache_disabled_when_dir_empty(self) -> None:
        with (
            patch("core.config.settings.tts_engine", "edge"),
            patch("core.config.settings.tts_cache_dir", ""),
        ):
            service = TTSService()
            self.assertIsNone(service._cache_dir)

            async def scenario() -> None:
                audio = await service.synthesize("测试", language="zh-CN")
                self.assertEqual(audio, b"")

            run(scenario())

    def test_diagnostics_include_voice_rate_volume_disk_hits(self) -> None:
        with patch("core.config.settings.tts_engine", "edge"):
            service = TTSService()
            diag = service.diagnostics
            self.assertIn("voice", diag)
            self.assertIn("rate", diag)
            self.assertIn("volume", diag)
            self.assertEqual(diag["volume"], "+0%")
            self.assertIn("diskHits", diag)
            self.assertEqual(diag["diskHits"], 0)

    def test_disk_cache_file_count_reflects_written_files(self) -> None:
        """磁盘缓存落盘后 disk_cache_file_count 反映实际文件数。"""
        fake_mp3 = b"\x49\x44\x33disk-file-count-mp3"
        with tempfile.TemporaryDirectory() as cache_dir:
            with (
                patch("core.config.settings.tts_engine", "edge"),
                patch("core.config.settings.tts_cache_dir", cache_dir),
            ):
                service = TTSService()
                with patch.object(TTSService, "_synthesize_edge", return_value=fake_mp3):
                    async def scenario() -> None:
                        await service.synthesize("缓存统计", language="zh-CN")

                    run(scenario())
                self.assertEqual(service.disk_cache_file_count, 1)
                self.assertEqual(service.diagnostics["diskCacheFiles"], 1)

    def test_disk_cache_file_count_zero_when_dir_disabled(self) -> None:
        service = TTSService()
        self.assertEqual(service.disk_cache_file_count, 0)
        self.assertIn("diskCacheFiles", service.diagnostics)


if __name__ == "__main__":
    unittest.main()
