"""Unit tests for Redis context manager key construction and URL redaction."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.context_manager import ContextManager, redact_url


class RedisKeyTests(unittest.TestCase):
    def test_session_key_uses_app_prefix(self) -> None:
        self.assertEqual(
            ContextManager._session_key("abc_123", "meta"),
            "ai-interpreter:session:abc_123:meta",
        )

    def test_session_key_rejects_invalid_characters(self) -> None:
        with self.assertRaises(ValueError):
            ContextManager._session_key("bad/session", "meta")

    def test_session_key_rejects_overlong_ids(self) -> None:
        with self.assertRaises(ValueError):
            ContextManager._session_key("x" * 65, "meta")


class UrlRedactionTests(unittest.TestCase):
    def test_redacts_password_in_redis_url(self) -> None:
        self.assertEqual(
            redact_url("redis://:secret@localhost:6379/0"),
            "redis://:***@localhost:6379/0",
        )

    def test_keeps_url_without_credentials_unchanged(self) -> None:
        url = "redis://localhost:6379/0"
        self.assertEqual(redact_url(url), url)

    def test_keeps_username_but_redacts_password(self) -> None:
        self.assertEqual(
            redact_url("redis://user:pass@localhost:6379/0"),
            "redis://user:***@localhost:6379/0",
        )

    def test_redacts_ipv6_url_keeping_brackets(self) -> None:
        self.assertEqual(
            redact_url("redis://:secret@[::1]:6379/0"),
            "redis://:***@[::1]:6379/0",
        )


if __name__ == "__main__":
    unittest.main()
