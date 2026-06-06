"""Unit tests for endurance baseline preflight reporting."""

from __future__ import annotations

import unittest

from tools.endurance_preflight import build_report, is_placeholder_value, redact_url


class EndurancePreflightTests(unittest.TestCase):
    def test_redact_url_removes_credentials(self) -> None:
        redacted = redact_url("redis://user:secret@localhost:6379/0?x=1")

        self.assertEqual(redacted, "redis://***@localhost:6379/0")

    def test_placeholder_values_do_not_count_as_keys(self) -> None:
        self.assertTrue(is_placeholder_value("your-anthropic-api-key-here"))
        self.assertFalse(is_placeholder_value("sk-realistic-prefix"))

    def test_report_blocks_missing_provider_key_and_cuda_mismatch(self) -> None:
        report = build_report(
            redis_check={"ok": True},
            provider_check={
                "supported": True,
                "engine": "claude",
                "model": "claude-sonnet-4-20250514",
                "required_key": "ANTHROPIC_API_KEY",
                "key_present": False,
            },
            whisper_check={
                "engine": "whisper",
                "package_present": True,
                "device": "cuda",
                "cuda_available": False,
                "model_load_checked": False,
            },
        )

        self.assertEqual(report["status"], "blocked")
        self.assertIn(
            "ANTHROPIC_API_KEY is missing or still uses a placeholder value.",
            report["blockers"],
        )
        self.assertIn(
            "WHISPER_DEVICE is cuda, but no CUDA device is available.",
            report["blockers"],
        )

    def test_report_ready_when_required_checks_pass(self) -> None:
        report = build_report(
            redis_check={"ok": True},
            provider_check={
                "supported": True,
                "engine": "openai",
                "model": "gpt-4o",
                "required_key": "OPENAI_API_KEY",
                "key_present": True,
            },
            whisper_check={
                "engine": "whisper",
                "package_present": True,
                "device": "cpu",
                "cuda_available": False,
                "model_load_checked": False,
            },
        )

        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["blockers"], [])


if __name__ == "__main__":
    unittest.main()
