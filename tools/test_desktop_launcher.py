"""Unit tests for desktop launcher startup helpers."""

from __future__ import annotations

import socket
import unittest
from unittest.mock import patch

from tools import desktop_launcher


class DesktopLauncherTests(unittest.TestCase):
    def test_resolve_backend_port_uses_fallback_when_port_is_occupied(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
            occupied.bind((desktop_launcher.HOST, 0))
            occupied.listen()
            requested_port = int(occupied.getsockname()[1])

            with (
                patch.object(desktop_launcher, "is_backend_healthy", return_value=False),
                patch.object(desktop_launcher, "write_log"),
            ):
                selected_port = desktop_launcher.resolve_backend_port(requested_port)

        self.assertNotEqual(selected_port, requested_port)
        self.assertTrue(desktop_launcher.is_port_available(selected_port))

    def test_resolve_backend_port_reuses_healthy_requested_port(self) -> None:
        with patch.object(desktop_launcher, "is_backend_healthy", return_value=True):
            selected_port = desktop_launcher.resolve_backend_port(8123)

        self.assertEqual(selected_port, 8123)

    def test_build_backend_environment_applies_light_profile_defaults(self) -> None:
        with (
            patch.dict(desktop_launcher.os.environ, {}, clear=True),
            patch.object(desktop_launcher, "write_log"),
        ):
            env = desktop_launcher.build_backend_environment(8123, "light")

        self.assertEqual(env["PORT"], "8123")
        self.assertEqual(env["ASR_ENGINE"], "whisper")
        self.assertEqual(env["WHISPER_MODEL"], "small")
        self.assertEqual(env["WHISPER_DEVICE"], "cpu")
        self.assertEqual(env["WHISPER_COMPUTE_TYPE"], "int8")

    def test_build_backend_environment_applies_remote_profile_defaults(self) -> None:
        settings = desktop_launcher.DesktopSettings(
            asr_model="whisper-1",
            asr_openai_base_url="https://api.openai.com/v1",
            asr_openai_api_key="local-asr-key",
        )

        with (
            patch.dict(desktop_launcher.os.environ, {}, clear=True),
            patch.object(desktop_launcher, "write_log"),
        ):
            env = desktop_launcher.build_backend_environment(8123, "remote", settings)

        self.assertEqual(env["PORT"], "8123")
        self.assertEqual(env["ASR_ENGINE"], "openai")
        self.assertEqual(env["ASR_OPENAI_MODEL"], "whisper-1")
        self.assertEqual(env["ASR_OPENAI_BASE_URL"], "https://api.openai.com/v1")
        self.assertEqual(env["ASR_OPENAI_API_KEY"], "local-asr-key")
        self.assertNotIn("WHISPER_MODEL", env)
        self.assertNotIn("WHISPER_DEVICE", env)
        self.assertNotIn("WHISPER_COMPUTE_TYPE", env)

    def test_build_backend_environment_preserves_explicit_process_env(self) -> None:
        with (
            patch.dict(
                desktop_launcher.os.environ,
                {
                    "ASR_ENGINE": "custom",
                    "WHISPER_MODEL": "base",
                    "WHISPER_DEVICE": "cuda",
                    "WHISPER_COMPUTE_TYPE": "float16",
                },
                clear=True,
            ),
            patch.object(desktop_launcher, "write_log"),
        ):
            env = desktop_launcher.build_backend_environment(8123, "light")

        self.assertEqual(env["ASR_ENGINE"], "custom")
        self.assertEqual(env["WHISPER_MODEL"], "base")
        self.assertEqual(env["WHISPER_DEVICE"], "cuda")
        self.assertEqual(env["WHISPER_COMPUTE_TYPE"], "float16")

    def test_build_backend_environment_replaces_blank_process_env(self) -> None:
        with (
            patch.dict(
                desktop_launcher.os.environ,
                {
                    "ASR_ENGINE": "",
                    "WHISPER_MODEL": "",
                    "WHISPER_DEVICE": " ",
                    "WHISPER_COMPUTE_TYPE": "",
                },
                clear=True,
            ),
            patch.object(desktop_launcher, "write_log"),
        ):
            env = desktop_launcher.build_backend_environment(8123, "light")

        self.assertEqual(env["ASR_ENGINE"], "whisper")
        self.assertEqual(env["WHISPER_MODEL"], "small")
        self.assertEqual(env["WHISPER_DEVICE"], "cpu")
        self.assertEqual(env["WHISPER_COMPUTE_TYPE"], "int8")

    def test_build_backend_environment_env_profile_does_not_inject_asr_values(self) -> None:
        settings = desktop_launcher.DesktopSettings(
            asr_model="whisper-1",
            asr_openai_base_url="https://api.openai.com/v1",
            asr_openai_api_key="local-asr-key",
        )

        with (
            patch.dict(desktop_launcher.os.environ, {}, clear=True),
            patch.object(desktop_launcher, "write_log"),
        ):
            env = desktop_launcher.build_backend_environment(8123, "env", settings)

        self.assertEqual(env["PORT"], "8123")
        self.assertNotIn("ASR_ENGINE", env)
        self.assertNotIn("ASR_OPENAI_MODEL", env)
        self.assertNotIn("ASR_OPENAI_BASE_URL", env)
        self.assertNotIn("ASR_OPENAI_API_KEY", env)
        self.assertNotIn("WHISPER_MODEL", env)
        self.assertNotIn("WHISPER_DEVICE", env)
        self.assertNotIn("WHISPER_COMPUTE_TYPE", env)

    def test_build_backend_environment_applies_local_desktop_settings(self) -> None:
        settings = desktop_launcher.DesktopSettings(
            nmt_engine="openai",
            nmt_model="gpt-4o-mini",
            openai_base_url="https://example.test/v1",
            openai_api_key="local-openai-key",
            anthropic_api_key="local-anthropic-key",
            asr_model="whisper-1",
            asr_openai_base_url="https://api.openai.com/v1",
            asr_openai_api_key="local-asr-key",
            source_language="ja",
        )

        with (
            patch.dict(desktop_launcher.os.environ, {}, clear=True),
            patch.object(desktop_launcher, "write_log"),
        ):
            env = desktop_launcher.build_backend_environment(8123, "env", settings)

        self.assertEqual(env["NMT_ENGINE"], "openai")
        self.assertEqual(env["NMT_MODEL"], "gpt-4o-mini")
        self.assertEqual(env["OPENAI_BASE_URL"], "https://example.test/v1")
        self.assertEqual(env["OPENAI_API_KEY"], "local-openai-key")
        self.assertEqual(env["ANTHROPIC_API_KEY"], "local-anthropic-key")
        self.assertNotIn("ASR_OPENAI_MODEL", env)
        self.assertNotIn("ASR_OPENAI_BASE_URL", env)
        self.assertNotIn("ASR_OPENAI_API_KEY", env)
        self.assertEqual(env["SOURCE_LANGUAGE"], "ja")

    def test_build_backend_environment_preserves_process_env_over_local_settings(self) -> None:
        settings = desktop_launcher.DesktopSettings(
            nmt_engine="openai",
            nmt_model="local-model",
            source_language="fr",
        )

        with (
            patch.dict(
                desktop_launcher.os.environ,
                {
                    "NMT_MODEL": "env-model",
                    "SOURCE_LANGUAGE": "en",
                },
                clear=True,
            ),
            patch.object(desktop_launcher, "write_log"),
        ):
            env = desktop_launcher.build_backend_environment(8123, "env", settings)

        self.assertEqual(env["NMT_ENGINE"], "openai")
        self.assertEqual(env["NMT_MODEL"], "env-model")
        self.assertEqual(env["SOURCE_LANGUAGE"], "en")

    def test_resolve_desktop_asr_profile_uses_local_settings_when_no_override(self) -> None:
        settings = desktop_launcher.DesktopSettings(asr_profile="gpu")

        with patch.dict(desktop_launcher.os.environ, {}, clear=True):
            profile = desktop_launcher.resolve_desktop_asr_profile(None, settings)

        self.assertEqual(profile, "gpu")

    def test_resolve_desktop_asr_profile_defaults_to_remote(self) -> None:
        with patch.dict(desktop_launcher.os.environ, {}, clear=True):
            profile = desktop_launcher.resolve_desktop_asr_profile(
                None,
                desktop_launcher.DesktopSettings(),
            )

        self.assertEqual(profile, "remote")

    def test_resolve_desktop_asr_profile_prefers_cli_then_env(self) -> None:
        settings = desktop_launcher.DesktopSettings(asr_profile="gpu")

        with patch.dict(
            desktop_launcher.os.environ,
            {desktop_launcher.DESKTOP_ASR_PROFILE_ENV: "cpu"},
            clear=True,
        ):
            env_profile = desktop_launcher.resolve_desktop_asr_profile(None, settings)
            cli_profile = desktop_launcher.resolve_desktop_asr_profile("env", settings)

        self.assertEqual(env_profile, "cpu")
        self.assertEqual(cli_profile, "env")

    def test_normalize_desktop_settings_rejects_unsupported_values(self) -> None:
        settings = desktop_launcher.normalize_desktop_settings({
            "uiLanguage": "zh-CN",
            "translation": {
                "engine": "prompt-injection",
                "model": " model ",
                "openaiBaseUrl": " https://example.test/v1 ",
            },
            "asr": {
                "model": " whisper-1 ",
                "openaiBaseUrl": " https://api.openai.com/v1 ",
                "openaiApiKey": " asr-key ",
            },
            "runtime": {
                "asrProfile": "too-large",
                "sourceLanguage": "ja",
            },
        })

        self.assertEqual(settings.ui_language, "zh-CN")
        self.assertEqual(settings.nmt_engine, "")
        self.assertEqual(settings.nmt_model, "model")
        self.assertEqual(settings.openai_base_url, "https://example.test/v1")
        self.assertEqual(settings.asr_model, "whisper-1")
        self.assertEqual(settings.asr_openai_base_url, "https://api.openai.com/v1")
        self.assertEqual(settings.asr_openai_api_key, "asr-key")
        self.assertEqual(settings.asr_profile, "")
        self.assertEqual(settings.source_language, "ja")

    def test_create_desktop_url_injects_backend_ws_query_param(self) -> None:
        url = desktop_launcher.append_query_param(
            "http://127.0.0.1:4500/?surface=main",
            desktop_launcher.WS_URL_QUERY_PARAM,
            "ws://127.0.0.1:8123/api/v1/ws/translate",
        )

        self.assertEqual(
            url,
            (
                "http://127.0.0.1:4500/?surface=main&"
                "wsUrl=ws%3A%2F%2F127.0.0.1%3A8123%2Fapi%2Fv1%2Fws%2Ftranslate"
            ),
        )

    def test_create_frontend_app_url_injects_backend_ws_query_param(self) -> None:
        url = desktop_launcher.create_frontend_app_url(
            "http://127.0.0.1:4500/",
            "ws://127.0.0.1:8123/api/v1/ws/translate",
        )

        self.assertEqual(
            url,
            (
                "http://127.0.0.1:4500/?"
                "wsUrl=ws%3A%2F%2F127.0.0.1%3A8123%2Fapi%2Fv1%2Fws%2Ftranslate"
            ),
        )

    def test_launch_web_browser_opens_default_browser(self) -> None:
        with (
            patch.object(desktop_launcher.webbrowser, "open", return_value=True) as open_browser,
            patch.object(desktop_launcher, "write_log"),
        ):
            app_url = desktop_launcher.launch_web_browser(
                "http://127.0.0.1:4500/",
                "ws://127.0.0.1:8123/api/v1/ws/translate",
            )

        self.assertEqual(
            app_url,
            (
                "http://127.0.0.1:4500/?"
                "wsUrl=ws%3A%2F%2F127.0.0.1%3A8123%2Fapi%2Fv1%2Fws%2Ftranslate"
            ),
        )
        open_browser.assert_called_once_with(app_url, new=2)

    def test_main_web_mode_does_not_launch_electron(self) -> None:
        class FakeServer:
            def __init__(self) -> None:
                self.is_shutdown = False
                self.is_closed = False

            def shutdown(self) -> None:
                self.is_shutdown = True

            def server_close(self) -> None:
                self.is_closed = True

        fake_server = FakeServer()

        with (
            patch.object(desktop_launcher.sys, "argv", ["desktop_launcher.py", "--mode", "web", "--no-splash"]),
            patch.object(desktop_launcher, "reset_log"),
            patch.object(desktop_launcher, "write_log"),
            patch.object(desktop_launcher, "load_desktop_settings", return_value=desktop_launcher.DesktopSettings()),
            patch.object(desktop_launcher, "ensure_frontend_build"),
            patch.object(
                desktop_launcher,
                "start_frontend_server",
                return_value=(fake_server, "http://127.0.0.1:4500/"),
            ),
            patch.object(desktop_launcher, "resolve_backend_port", return_value=8123),
            patch.object(desktop_launcher, "start_backend", return_value=None),
            patch.object(
                desktop_launcher,
                "launch_web_browser",
                return_value="http://127.0.0.1:4500/?wsUrl=runtime",
            ) as launch_web_browser,
            patch.object(desktop_launcher, "wait_for_web_session"),
            patch.object(desktop_launcher, "launch_desktop_window") as launch_desktop_window,
        ):
            result = desktop_launcher.main()

        self.assertEqual(result, 0)
        self.assertTrue(fake_server.is_shutdown)
        self.assertTrue(fake_server.is_closed)
        launch_web_browser.assert_called_once_with(
            "http://127.0.0.1:4500/",
            "ws://127.0.0.1:8123/api/v1/ws/translate",
        )
        launch_desktop_window.assert_not_called()


if __name__ == "__main__":
    unittest.main()
