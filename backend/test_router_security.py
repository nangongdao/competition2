"""Security tests for the API router WebSocket origin validation."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from api.router import _is_allowed_ws_origin


class WsOriginValidationTests(unittest.TestCase):
    def test_allows_registered_local_origin(self) -> None:
        self.assertTrue(_is_allowed_ws_origin("http://127.0.0.1:5173"))

    def test_allows_localhost_origin(self) -> None:
        self.assertTrue(_is_allowed_ws_origin("http://localhost:5173"))

    def test_allows_electron_file_origin(self) -> None:
        self.assertTrue(_is_allowed_ws_origin("file://"))

    def test_rejects_arbitrary_https_origin(self) -> None:
        self.assertFalse(_is_allowed_ws_origin("https://evil.example.com"))

    def test_rejects_arbitrary_http_origin(self) -> None:
        self.assertFalse(_is_allowed_ws_origin("http://attacker.local:9999"))

    def test_allows_originless_native_clients(self) -> None:
        # 非浏览器客户端（如测试工具）不带 Origin，桌面场景放行。
        self.assertTrue(_is_allowed_ws_origin(None))


if __name__ == "__main__":
    unittest.main()
