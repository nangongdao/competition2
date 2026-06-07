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
        self.assertEqual(env["WHISPER_MODEL"], "small")
        self.assertEqual(env["WHISPER_DEVICE"], "cpu")
        self.assertEqual(env["WHISPER_COMPUTE_TYPE"], "int8")

    def test_build_backend_environment_preserves_explicit_process_env(self) -> None:
        with (
            patch.dict(
                desktop_launcher.os.environ,
                {
                    "WHISPER_MODEL": "base",
                    "WHISPER_DEVICE": "cuda",
                    "WHISPER_COMPUTE_TYPE": "float16",
                },
                clear=True,
            ),
            patch.object(desktop_launcher, "write_log"),
        ):
            env = desktop_launcher.build_backend_environment(8123, "light")

        self.assertEqual(env["WHISPER_MODEL"], "base")
        self.assertEqual(env["WHISPER_DEVICE"], "cuda")
        self.assertEqual(env["WHISPER_COMPUTE_TYPE"], "float16")

    def test_build_backend_environment_replaces_blank_process_env(self) -> None:
        with (
            patch.dict(
                desktop_launcher.os.environ,
                {
                    "WHISPER_MODEL": "",
                    "WHISPER_DEVICE": " ",
                    "WHISPER_COMPUTE_TYPE": "",
                },
                clear=True,
            ),
            patch.object(desktop_launcher, "write_log"),
        ):
            env = desktop_launcher.build_backend_environment(8123, "light")

        self.assertEqual(env["WHISPER_MODEL"], "small")
        self.assertEqual(env["WHISPER_DEVICE"], "cpu")
        self.assertEqual(env["WHISPER_COMPUTE_TYPE"], "int8")

    def test_build_backend_environment_env_profile_does_not_inject_asr_values(self) -> None:
        with (
            patch.dict(desktop_launcher.os.environ, {}, clear=True),
            patch.object(desktop_launcher, "write_log"),
        ):
            env = desktop_launcher.build_backend_environment(8123, "env")

        self.assertEqual(env["PORT"], "8123")
        self.assertNotIn("WHISPER_MODEL", env)
        self.assertNotIn("WHISPER_DEVICE", env)
        self.assertNotIn("WHISPER_COMPUTE_TYPE", env)

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


if __name__ == "__main__":
    unittest.main()
