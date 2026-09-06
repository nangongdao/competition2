"""Unit tests for backend settings loading."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.config import ENV_FILE_PATHS, REPO_ROOT, Settings


class SettingsConfigTests(unittest.TestCase):
    def test_default_env_files_include_local_backend_override(self) -> None:
        expected_paths = (
            REPO_ROOT / ".env",
            BACKEND_ROOT / ".env",
            BACKEND_ROOT / ".env.local",
        )

        self.assertEqual(ENV_FILE_PATHS, expected_paths)

    def test_later_dotenv_files_override_earlier_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_env = Path(temp_dir) / "root.env"
            backend_env = Path(temp_dir) / "backend.env"
            local_env = Path(temp_dir) / "local.env"
            root_env.write_text(
                "ANTHROPIC_API_KEY=from-root\nNMT_ENGINE=claude\n",
                encoding="utf-8",
            )
            backend_env.write_text(
                "ANTHROPIC_API_KEY=from-backend\n",
                encoding="utf-8",
            )
            local_env.write_text(
                "ANTHROPIC_API_KEY=from-local\nUNKNOWN_LOCAL_VALUE=ignored\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                settings = Settings(_env_file=(root_env, backend_env, local_env))

        self.assertEqual(settings.anthropic_api_key, "from-local")
        self.assertEqual(settings.nmt_engine, "claude")

    def test_environment_variables_override_dotenv_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            local_env = Path(temp_dir) / "local.env"
            local_env.write_text(
                "ANTHROPIC_API_KEY=from-local\n",
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {"ANTHROPIC_API_KEY": "from-env"},
                clear=True,
            ):
                settings = Settings(_env_file=local_env)

        self.assertEqual(settings.anthropic_api_key, "from-env")

    def test_builtin_asr_defaults_are_low_resource(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=())

        self.assertEqual(settings.whisper_model, "small")
        self.assertEqual(settings.whisper_device, "cpu")
        self.assertEqual(settings.whisper_compute_type, "int8")

    def test_default_host_is_loopback_only(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=())

        self.assertEqual(settings.host, "127.0.0.1")

    def test_default_cors_origins_are_local_frontends(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=())

        self.assertIn("http://127.0.0.1:5173", settings.allowed_origin_list)
        self.assertNotIn("*", settings.allowed_origin_list)

    def test_allowed_origins_parses_comma_separated_list(self) -> None:
        with patch.dict(
            os.environ,
            {"ALLOWED_ORIGINS": "http://a.local, ,http://b.local"},
            clear=True,
        ):
            settings = Settings(_env_file=())

        self.assertEqual(settings.allowed_origin_list, ["http://a.local", "http://b.local"])

    def test_audio_frame_limits_have_sane_defaults(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=())

        self.assertEqual(settings.audio_max_chunk_bytes, 64 * 1024)
        self.assertEqual(settings.audio_max_chunks_per_second, 20)
        self.assertEqual(settings.redis_key_prefix, "ai-interpreter")

    def test_vad_parameters_are_configurable_and_defaulted(self) -> None:
        """V2.4：VAD 切分参数可通过环境变量覆盖，默认值符合 ROADMAP。"""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=())

        self.assertEqual(settings.vad_threshold, 0.5)
        self.assertEqual(settings.vad_min_silence_ms, 500)
        self.assertEqual(settings.vad_min_speech_ms, 250)
        self.assertEqual(settings.vad_max_sentence_s, 15)

        with patch.dict(
            os.environ,
            {
                "VAD_MIN_SILENCE_MS": "800",
                "VAD_MIN_SPEECH_MS": "300",
                "VAD_MAX_SENTENCE_S": "20",
                "VAD_THRESHOLD": "0.7",
            },
            clear=True,
        ):
            overridden = Settings(_env_file=())

        self.assertEqual(overridden.vad_min_silence_ms, 800)
        self.assertEqual(overridden.vad_min_speech_ms, 300)
        self.assertEqual(overridden.vad_max_sentence_s, 20)
        self.assertEqual(overridden.vad_threshold, 0.7)


if __name__ == "__main__":
    unittest.main()
