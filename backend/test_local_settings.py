"""Unit tests for local settings persistence."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.local_settings import (
    LocalAsrSettings,
    LocalRuntimeSettings,
    LocalSettings,
    LocalSubtitleStyleSettings,
    LocalTranslationSettings,
    create_default_local_settings,
    create_settings_file_payload,
    create_settings_snapshot,
    merge_local_settings_update,
    read_local_settings,
    save_local_settings_update,
)


class LocalSettingsTests(unittest.TestCase):
    def test_default_settings_use_remote_asr_profile(self) -> None:
        settings = create_default_local_settings()

        self.assertEqual(settings.runtime.asr_profile, "remote")

    def test_snapshot_exposes_only_secret_presence(self) -> None:
        settings = LocalSettings(
            ui_language="en-US",
            translation=LocalTranslationSettings(
                engine="openai",
                model="gpt-4o-mini",
                openai_base_url="https://example.test/v1",
                openai_api_key="real-openai-key",
                anthropic_api_key="",
            ),
            asr=LocalAsrSettings(
                model="whisper-1",
                openai_base_url="https://api.openai.com/v1",
                openai_api_key="real-asr-key",
            ),
            runtime=LocalRuntimeSettings(
                asr_profile="light",
                source_language="ja",
                target_language="zh-CN",
            ),
        )

        snapshot = create_settings_snapshot(settings, Path("local.json"))

        translation = snapshot["translation"]
        self.assertIsInstance(translation, dict)
        self.assertEqual(translation["hasOpenaiApiKey"], True)
        self.assertEqual(translation["hasAnthropicApiKey"], False)
        self.assertNotIn("openaiApiKey", translation)
        self.assertNotIn("anthropicApiKey", translation)
        asr = snapshot["asr"]
        self.assertIsInstance(asr, dict)
        self.assertEqual(asr["model"], "whisper-1")
        self.assertEqual(asr["hasOpenaiApiKey"], True)
        self.assertNotIn("openaiApiKey", asr)

    def test_merge_preserves_existing_secret_when_update_is_blank(self) -> None:
        current = LocalSettings(
            ui_language="zh-CN",
            translation=LocalTranslationSettings(
                engine="openai",
                model="local-model",
                openai_base_url="https://example.test/v1",
                openai_api_key="saved-openai-key",
                anthropic_api_key="saved-anthropic-key",
            ),
            asr=LocalAsrSettings(
                model="whisper-1",
                openai_base_url="https://api.openai.com/v1",
                openai_api_key="saved-asr-key",
            ),
            runtime=LocalRuntimeSettings(
                asr_profile="light",
                source_language="en",
                target_language="zh-CN",
            ),
        )

        settings = merge_local_settings_update(
            {
                "translation": {
                    "engine": "claude",
                    "model": "claude-sonnet-4-20250514",
                    "openaiApiKey": " ",
                    "anthropicApiKey": "",
                },
                "asr": {
                    "model": "gpt-4o-mini-transcribe",
                    "openaiApiKey": "",
                }
            },
            current,
        )

        self.assertEqual(settings.translation.engine, "claude")
        self.assertEqual(settings.translation.model, "claude-sonnet-4-20250514")
        self.assertEqual(settings.translation.openai_api_key, "saved-openai-key")
        self.assertEqual(settings.translation.anthropic_api_key, "saved-anthropic-key")
        self.assertEqual(settings.asr.model, "gpt-4o-mini-transcribe")
        self.assertEqual(settings.asr.openai_api_key, "saved-asr-key")

    def test_merge_clears_secret_only_when_requested(self) -> None:
        current = LocalSettings(
            ui_language="zh-CN",
            translation=LocalTranslationSettings(
                engine="openai",
                model="gpt-4o-mini",
                openai_base_url="https://api.openai.com/v1",
                openai_api_key="saved-openai-key",
                anthropic_api_key="saved-anthropic-key",
            ),
            asr=LocalAsrSettings(
                model="whisper-1",
                openai_base_url="https://api.openai.com/v1",
                openai_api_key="saved-asr-key",
            ),
            runtime=LocalRuntimeSettings(
                asr_profile="light",
                source_language="en",
                target_language="zh-CN",
            ),
        )

        settings = merge_local_settings_update(
            {
                "translation": {
                    "clearOpenaiApiKey": True,
                    "anthropicApiKey": "new-anthropic-key",
                },
                "asr": {
                    "clearOpenaiApiKey": True,
                }
            },
            current,
        )

        self.assertEqual(settings.translation.openai_api_key, "")
        self.assertEqual(settings.translation.anthropic_api_key, "new-anthropic-key")
        self.assertEqual(settings.asr.openai_api_key, "")

    def test_save_local_settings_update_writes_normalized_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            local_path = Path(temp_dir) / "desktop-settings.local.json"
            example_path = Path(temp_dir) / "desktop-settings.example.json"
            example_path.write_text(
                """{
  "uiLanguage": "zh-CN",
  "translation": {
    "engine": "openai",
    "model": "gpt-4o-mini",
    "openaiBaseUrl": "https://api.openai.com/v1",
    "openaiApiKey": "",
    "anthropicApiKey": ""
  },
  "asr": {
    "model": "whisper-1",
    "openaiBaseUrl": "https://api.openai.com/v1",
    "openaiApiKey": ""
  },
  "runtime": {
    "asrProfile": "light",
    "sourceLanguage": "en",
    "targetLanguage": "zh-CN"
  }
}
""",
                encoding="utf-8",
            )

            settings = save_local_settings_update(
                {
                    "uiLanguage": "en-US",
                    "translation": {
                        "engine": "invalid",
                        "model": " custom-model ",
                        "openaiBaseUrl": " https://example.test/v1 ",
                        "openaiApiKey": " local-key ",
                    },
                    "asr": {
                        "model": " gpt-4o-mini-transcribe ",
                        "openaiBaseUrl": " https://api.openai.com/v1 ",
                        "openaiApiKey": " asr-key ",
                    },
                    "runtime": {
                        "asrProfile": "env",
                        "sourceLanguage": "fr",
                        "targetLanguage": "en",
                    },
                },
                local_path,
                example_path,
            )
            persisted = read_local_settings(local_path, example_path)

        self.assertEqual(settings.ui_language, "en-US")
        self.assertEqual(settings.translation.engine, "openai")
        self.assertEqual(settings.translation.model, "custom-model")
        self.assertEqual(settings.translation.openai_api_key, "local-key")
        self.assertEqual(settings.asr.model, "gpt-4o-mini-transcribe")
        self.assertEqual(settings.asr.openai_base_url, "https://api.openai.com/v1")
        self.assertEqual(settings.asr.openai_api_key, "asr-key")
        self.assertEqual(persisted, settings)
        self.assertEqual(
            create_settings_file_payload(persisted)["asr"],
            {
                "model": "gpt-4o-mini-transcribe",
                "openaiBaseUrl": "https://api.openai.com/v1",
                "openaiApiKey": "asr-key",
            },
        )
        self.assertEqual(
            create_settings_file_payload(persisted)["runtime"],
            {"asrProfile": "env", "sourceLanguage": "fr", "targetLanguage": "en"},
        )

    def test_snapshot_exposes_subtitle_style_config(self) -> None:
        settings = LocalSettings(
            ui_language="zh-CN",
            translation=LocalTranslationSettings(
                engine="openai",
                model="gpt-4o-mini",
                openai_base_url="https://api.openai.com/v1",
                openai_api_key="",
                anthropic_api_key="",
            ),
            asr=LocalAsrSettings(
                model="whisper-1",
                openai_base_url="https://api.openai.com/v1",
                openai_api_key="",
            ),
            runtime=LocalRuntimeSettings(
                asr_profile="remote",
                source_language="en",
                target_language="zh-CN",
            ),
            subtitle_style=LocalSubtitleStyleSettings(
                font_size=30,
                font_color="#f0f0f0",
                background_color="#0b0f1a",
                background_opacity=0.82,
                position="top",
            ),
        )

        snapshot = create_settings_snapshot(settings, Path("local.json"))
        subtitle_style = snapshot["subtitleStyle"]
        self.assertIsInstance(subtitle_style, dict)
        self.assertEqual(subtitle_style["fontSize"], 30)
        self.assertEqual(subtitle_style["fontColor"], "#f0f0f0")
        self.assertEqual(subtitle_style["backgroundColor"], "#0b0f1a")
        self.assertEqual(subtitle_style["backgroundOpacity"], 0.82)
        self.assertEqual(subtitle_style["position"], "top")

    def test_merge_subtitle_style_clamps_and_validates_values(self) -> None:
        current = create_default_local_settings()
        settings = merge_local_settings_update(
            {
                "subtitleStyle": {
                    "fontSize": 999,
                    "fontColor": "not-a-color",
                    "backgroundColor": "#112233",
                    "backgroundOpacity": -0.5,
                    "position": "middle",
                }
            },
            current,
        )

        self.assertEqual(settings.subtitle_style.font_size, 36)
        self.assertEqual(settings.subtitle_style.font_color, "#ffffff")
        self.assertEqual(settings.subtitle_style.background_color, "#112233")
        self.assertEqual(settings.subtitle_style.background_opacity, 0.0)
        self.assertEqual(settings.subtitle_style.position, "middle")

    def test_subtitle_style_defaults_persist_through_file_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            local_path = Path(temp_dir) / "desktop-settings.local.json"
            example_path = Path(temp_dir) / "desktop-settings.example.json"
            example_path.write_text(
                '{"uiLanguage": "zh-CN"}',
                encoding="utf-8",
            )

            settings = save_local_settings_update(
                {"subtitleStyle": {"fontSize": 26, "position": "bottom"}},
                local_path,
                example_path,
            )
            persisted = read_local_settings(local_path, example_path)

        self.assertEqual(settings.subtitle_style.font_size, 26)
        self.assertEqual(persisted.subtitle_style, settings.subtitle_style)
        payload = create_settings_file_payload(persisted)
        self.assertEqual(
            payload["subtitleStyle"],
            {
                "fontSize": 26,
                "fontColor": "#ffffff",
                "backgroundColor": "#0a0e16",
                "backgroundOpacity": 0.78,
                "position": "bottom",
            },
        )


if __name__ == "__main__":
    unittest.main()
