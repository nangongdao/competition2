"""Unit tests for subtitle artifact validation tooling."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.subtitle_artifact_validator import (
    ArtifactValidationError,
    build_validation_report,
    validate_artifact,
    validate_artifact_text,
)


class SubtitleArtifactValidatorTests(unittest.TestCase):
    def test_validate_srt_reports_timeline_and_revision_markers(self) -> None:
        report = validate_artifact_text(
            "\n".join([
                "1",
                "00:00:00,000 --> 00:00:01,000",
                "EN: Hello",
                "ZH: Ni hao",
                "",
                "2",
                "00:00:02,000 --> 00:00:03,000",
                "ZH: Corrected",
                "[ASR revised]",
            ]),
            kind="srt",
            long_gap_ms=500,
        )

        self.assertTrue(report["is_usable"])
        self.assertEqual(report["warnings"], [])
        self.assertEqual(report["revision_markers"]["asr"], 1)
        summary = report["summary"]
        self.assertIsInstance(summary, dict)
        self.assertEqual(summary["cue_count"], 2)
        self.assertEqual(summary["gap_count"], 1)
        self.assertEqual(summary["long_gap_count"], 1)
        self.assertEqual(summary["max_gap_ms"], 1000)

    def test_validate_srt_rejects_overlapping_cues(self) -> None:
        report = validate_artifact_text(
            "\n".join([
                "1",
                "00:00:00,000 --> 00:00:02,000",
                "ZH: First",
                "",
                "2",
                "00:00:01,000 --> 00:00:03,000",
                "ZH: Second",
            ]),
            kind="srt",
        )

        self.assertFalse(report["is_usable"])
        self.assertIn("subtitle cues overlap", report["warnings"])
        summary = report["summary"]
        self.assertIsInstance(summary, dict)
        self.assertEqual(summary["overlap_count"], 1)

    def test_validate_empty_vtt_is_not_usable(self) -> None:
        report = validate_artifact_text("WEBVTT\n", kind="vtt")

        self.assertFalse(report["is_usable"])
        self.assertTrue(report["is_empty"])
        self.assertIn("artifact is empty", report["warnings"])

    def test_validate_markdown_notes_reports_readability(self) -> None:
        report = validate_artifact_text(
            "\n".join([
                "# AI Interpreter Learning Notes",
                "",
                "## Timeline",
                "",
                "### 1. 12:00:00",
                "",
                "- Source: Hello",
                "- Translation: Ni hao",
                "- Revision: Translation revised at 12:00:01",
            ]),
            kind="markdown",
        )

        self.assertTrue(report["is_usable"])
        self.assertEqual(report["revision_markers"]["translation"], 1)
        summary = report["summary"]
        self.assertIsInstance(summary, dict)
        self.assertEqual(summary["heading_count"], 3)
        self.assertEqual(summary["timeline_entry_count"], 1)
        self.assertEqual(summary["source_line_count"], 1)
        self.assertEqual(summary["translation_line_count"], 1)

    def test_validate_markdown_notes_ignores_utf8_bom(self) -> None:
        report = validate_artifact_text(
            "\ufeff" + "\n".join([
                "# AI Interpreter Learning Notes",
                "",
                "## Timeline",
                "",
                "### 1. 12:00:00",
                "",
                "- Source: Hello",
                "- Translation: Ni hao",
            ]),
            kind="markdown",
        )

        self.assertTrue(report["is_usable"])
        summary = report["summary"]
        self.assertIsInstance(summary, dict)
        self.assertTrue(summary["has_title"])
        self.assertEqual(summary["timeline_entry_count"], 1)

    def test_validate_plain_transcript_counts_entries(self) -> None:
        report = validate_artifact_text(
            "\n".join([
                "1. 12:00:00 [revised:translation_correction]",
                "EN: Hello",
                "ZH: Ni hao",
            ]),
            kind="txt",
        )

        self.assertTrue(report["is_usable"])
        self.assertEqual(report["revision_markers"]["translation"], 1)
        summary = report["summary"]
        self.assertIsInstance(summary, dict)
        self.assertEqual(summary["entry_count"], 1)
        self.assertEqual(summary["source_line_count"], 1)
        self.assertEqual(summary["translation_line_count"], 1)

    def test_validate_artifact_detects_kind_from_extension(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "session.vtt"
            path.write_text(
                "\n".join([
                    "WEBVTT",
                    "",
                    "00:00:00.000 --> 00:00:01.000",
                    "ZH: Ni hao",
                ]),
                encoding="utf-8",
            )

            report = validate_artifact(path)

        self.assertEqual(report["kind"], "vtt")
        self.assertTrue(report["is_usable"])

    def test_build_validation_report_counts_unusable_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            valid_path = Path(tmpdir) / "valid.txt"
            empty_path = Path(tmpdir) / "empty.txt"
            valid_path.write_text("1. 12:00:00\nEN: Hello\nZH: Ni hao\n", encoding="utf-8")
            empty_path.write_text("", encoding="utf-8")

            report = build_validation_report(
                [valid_path, empty_path],
                kind=None,
                long_gap_ms=5000,
            )

        self.assertEqual(report["artifact_count"], 2)
        self.assertEqual(report["usable_count"], 1)
        self.assertEqual(report["unusable_count"], 1)

    def test_validate_artifact_rejects_unknown_extension(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "session.bin"
            path.write_text("payload", encoding="utf-8")

            with self.assertRaises(ArtifactValidationError):
                validate_artifact(path)


if __name__ == "__main__":
    unittest.main()
