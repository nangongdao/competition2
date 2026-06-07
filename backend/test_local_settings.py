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
    "sourceLanguage": "en"
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
            {"asrProfile": "env", "sourceLanguage": "fr"},
        )


if __name__ == "__main__":
    unittest.main()
