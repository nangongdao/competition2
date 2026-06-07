"""Unit tests for the interpreter validation suite orchestrator."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.interpreter_validation_suite import (
    CommandResult,
    SuiteConfig,
    parse_args,
    run_suite,
)


class InterpreterValidationSuiteTests(unittest.TestCase):
    def test_preflight_only_passes_and_writes_combined_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config = make_config(
                root,
                run_endurance=False,
                artifact_paths=(),
            )
            calls: list[list[str]] = []

            def runner(command: list[str]) -> CommandResult:
                calls.append(command)
                write_json(
                    config.preflight_output_path,
                    {
                        "status": "ready",
                        "blockers": [],
                        "checks": {
                            "redis": {"ok": True, "url": "redis://localhost:6379/0"},
                            "provider": {
                                "engine": "openai",
                                "model": "test-model",
                                "required_key": "OPENAI_API_KEY",
                                "key_present": True,
                            },
                            "whisper": {
                                "engine": "whisper",
                                "package_present": True,
                                "model": "base",
                                "device": "cpu",
                                "compute_type": "int8",
                                "cuda_available": False,
                                "model_load_checked": False,
                            },
                        },
                    },
                )
                return CommandResult(exit_code=0, stdout="ok\n")

            exit_code, report = run_suite(config, command_runner=runner)

            self.assertEqual(exit_code, 0)
            self.assertEqual(report["status"], "passed")
            self.assertEqual(len(calls), 1)
            self.assertTrue(config.output_path.exists())
            steps = report["steps"]
            self.assertIsInstance(steps, list)
            self.assertEqual(steps[0]["status"], "passed")
            self.assertEqual(steps[1]["status"], "skipped")
            self.assertEqual(steps[2]["status"], "skipped")

    def test_blocked_preflight_skips_endurance(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config = make_config(root, run_endurance=True, artifact_paths=())
            calls: list[list[str]] = []

            def runner(command: list[str]) -> CommandResult:
                calls.append(command)
                write_json(
                    config.preflight_output_path,
                    {
                        "status": "blocked",
                        "blockers": ["OPENAI_API_KEY is missing."],
                        "checks": {
                            "redis": {"ok": True},
                            "provider": {
                                "engine": "openai",
                                "model": "test-model",
                                "required_key": "OPENAI_API_KEY",
                                "key_present": False,
                            },
                            "whisper": {"engine": "whisper", "package_present": True},
                        },
                    },
                )
                return CommandResult(exit_code=2, stderr="blocked\n")

            exit_code, report = run_suite(config, command_runner=runner)

            self.assertEqual(exit_code, 2)
            self.assertEqual(report["status"], "blocked")
            self.assertEqual(len(calls), 1)
            steps = report["steps"]
            self.assertIsInstance(steps, list)
            self.assertEqual(steps[0]["status"], "blocked")
            self.assertEqual(steps[1]["status"], "skipped")
            self.assertIn("Resolve preflight blockers", report["next_actions"][0])

    def test_artifact_only_run_passes_when_artifacts_are_usable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact_path = root / "session.srt"
            artifact_path.write_text("placeholder", encoding="utf-8")
            config = make_config(
                root,
                skip_preflight=True,
                run_endurance=False,
                artifact_paths=(artifact_path,),
            )

            def runner(command: list[str]) -> CommandResult:
                self.assertIn("tools/subtitle_artifact_validator.py", command)
                self.assertIn(str(artifact_path), command)
                write_json(
                    config.artifact_output_path,
                    {
                        "artifact_count": 1,
                        "usable_count": 1,
                        "unusable_count": 0,
                        "artifacts": [
                            {
                                "path": str(artifact_path),
                                "is_usable": True,
                            },
                        ],
                    },
                )
                return CommandResult(exit_code=0)

            exit_code, report = run_suite(config, command_runner=runner)

            self.assertEqual(exit_code, 0)
            self.assertEqual(report["status"], "passed")
            steps = report["steps"]
            self.assertIsInstance(steps, list)
            self.assertEqual(steps[0]["status"], "skipped")
            self.assertEqual(steps[2]["status"], "passed")
            summary = steps[2]["summary"]
            self.assertIsInstance(summary, dict)
            self.assertEqual(summary["usable_count"], 1)

    def test_unusable_artifacts_fail_the_suite(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact_path = root / "empty.vtt"
            artifact_path.write_text("WEBVTT\n", encoding="utf-8")
            config = make_config(
                root,
                skip_preflight=True,
                run_endurance=False,
                artifact_paths=(artifact_path,),
            )

            def runner(_command: list[str]) -> CommandResult:
                write_json(
                    config.artifact_output_path,
                    {
                        "artifact_count": 1,
                        "usable_count": 0,
                        "unusable_count": 1,
                        "artifacts": [
                            {
                                "path": str(artifact_path),
                                "is_usable": False,
                            },
                        ],
                    },
                )
                return CommandResult(exit_code=2, stderr="unusable\n")

            exit_code, report = run_suite(config, command_runner=runner)

            self.assertEqual(exit_code, 2)
            self.assertEqual(report["status"], "failed")
            steps = report["steps"]
            self.assertIsInstance(steps, list)
            summary = steps[2]["summary"]
            self.assertIsInstance(summary, dict)
            self.assertEqual(summary["unusable_paths"], [str(artifact_path)])

    def test_failed_child_does_not_reuse_stale_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config = make_config(root, skip_preflight=True, run_endurance=True)
            write_json(
                config.endurance_output_path,
                {
                    "session_id": "stale",
                    "summary": {"backend_received_ratio": 1.0},
                },
            )

            def runner(command: list[str]) -> CommandResult:
                self.assertIn("tools/endurance_runner.py", command)
                self.assertFalse(config.endurance_output_path.exists())
                return CommandResult(exit_code=2, stderr="connection failed\n")

            exit_code, report = run_suite(config, command_runner=runner)

            self.assertEqual(exit_code, 2)
            self.assertEqual(report["status"], "failed")
            steps = report["steps"]
            self.assertIsInstance(steps, list)
            summary = steps[1]["summary"]
            self.assertIsInstance(summary, dict)
            self.assertFalse(summary["report_available"])

    def test_parse_args_builds_endurance_thresholds_and_memory_options(self) -> None:
        config = parse_args([
            "--skip-preflight",
            "--run-endurance",
            "--duration-seconds",
            "1800",
            "--max-queue-depth",
            "8",
            "--min-received-ratio",
            "0.99",
            "--monitor-self",
            "--monitor-pid",
            "backend=1234",
            "--max-memory-growth-mb",
            "150",
            "--artifact",
            "exports/session.srt",
        ])

        self.assertTrue(config.skip_preflight)
        self.assertTrue(config.run_endurance)
        self.assertIn("--duration-seconds", config.endurance_args)
        self.assertIn("1800.0", config.endurance_args)
        self.assertIn("--monitor-self", config.endurance_args)
        self.assertIn("backend=1234", config.endurance_args)
        self.assertEqual(config.artifact_paths, (Path("exports/session.srt"),))


def make_config(
    root: Path,
    *,
    skip_preflight: bool = False,
    run_endurance: bool = False,
    artifact_paths: tuple[Path, ...] = (),
) -> SuiteConfig:
    return SuiteConfig(
        output_path=root / "suite.json",
        skip_preflight=skip_preflight,
        preflight_output_path=root / "preflight.json",
        load_whisper_model=False,
        run_endurance=run_endurance,
        endurance_output_path=root / "endurance.json",
        endurance_args=("--duration-seconds", "1"),
        artifact_paths=artifact_paths,
        artifact_output_path=root / "artifacts.json",
        artifact_kind=None,
        artifact_long_gap_ms=5000,
    )


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
