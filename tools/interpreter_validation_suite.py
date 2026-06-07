"""Coordinate AI interpreter readiness, endurance, and artifact validation.

This suite intentionally composes the existing validation tools instead of
duplicating their checks. It gives operators one JSON report that can be used
as evidence for real-session acceptance work.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
import time


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUITE_OUTPUT = Path("reports/interpreter-validation-latest.json")
DEFAULT_PREFLIGHT_OUTPUT = Path("reports/endurance-preflight-latest.json")
DEFAULT_ENDURANCE_OUTPUT = Path("reports/endurance-latest.json")
DEFAULT_ARTIFACT_OUTPUT = Path("reports/subtitle-artifacts-latest.json")
DEFAULT_WS_URL = "ws://localhost:8000/api/v1/ws/translate"
TEXT_EXCERPT_LIMIT = 2000


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class SuiteConfig:
    output_path: Path
    skip_preflight: bool
    preflight_output_path: Path
    load_whisper_model: bool
    run_endurance: bool
    endurance_output_path: Path
    endurance_args: tuple[str, ...]
    artifact_paths: tuple[Path, ...]
    artifact_output_path: Path
    artifact_kind: str | None
    artifact_long_gap_ms: int


CommandRunner = Callable[[list[str]], CommandResult]


def run_command(command: list[str]) -> CommandResult:
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return CommandResult(
        exit_code=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def run_suite(
    config: SuiteConfig,
    *,
    command_runner: CommandRunner = run_command,
) -> tuple[int, dict[str, object]]:
    steps: list[dict[str, object]] = []

    if config.skip_preflight:
        steps.append(build_skipped_step(
            name="preflight",
            reason="Skipped by --skip-preflight.",
        ))
        preflight_passed = True
    else:
        preflight_step = run_preflight_step(config, command_runner)
        steps.append(preflight_step)
        preflight_passed = preflight_step["status"] == "passed"

    if config.run_endurance:
        if preflight_passed:
            steps.append(run_endurance_step(config, command_runner))
        else:
            steps.append(build_skipped_step(
                name="endurance",
                reason=(
                    "Skipped because preflight did not pass. Use --skip-preflight "
                    "only when you intentionally want to run endurance without it."
                ),
            ))
    else:
        steps.append(build_skipped_step(
            name="endurance",
            reason="Skipped by default. Pass --run-endurance to collect a live baseline.",
        ))

    if config.artifact_paths:
        steps.append(run_artifact_step(config, command_runner))
    else:
        steps.append(build_skipped_step(
            name="artifacts",
            reason="No artifact paths were provided with --artifact.",
        ))

    report = build_suite_report(steps)
    write_report(config.output_path, report)
    return (0 if report["status"] == "passed" else 2), report


def run_preflight_step(
    config: SuiteConfig,
    command_runner: CommandRunner,
) -> dict[str, object]:
    command = [
        sys.executable,
        "tools/endurance_preflight.py",
        "--output",
        str(config.preflight_output_path),
    ]
    if config.load_whisper_model:
        command.append("--load-whisper-model")
    remove_existing_report(config.preflight_output_path)
    result = command_runner(command)
    child_report = load_json_report(config.preflight_output_path)
    status = "passed" if result.exit_code == 0 else "failed"
    if isinstance(child_report, dict) and child_report.get("status") == "blocked":
        status = "blocked"
    return build_executed_step(
        name="preflight",
        command=command,
        result=result,
        status=status,
        report_path=config.preflight_output_path,
        summary=summarize_preflight(child_report),
    )


def run_endurance_step(
    config: SuiteConfig,
    command_runner: CommandRunner,
) -> dict[str, object]:
    command = [
        sys.executable,
        "tools/endurance_runner.py",
        *config.endurance_args,
        "--output",
        str(config.endurance_output_path),
    ]
    remove_existing_report(config.endurance_output_path)
    result = command_runner(command)
    child_report = load_json_report(config.endurance_output_path)
    return build_executed_step(
        name="endurance",
        command=command,
        result=result,
        status="passed" if result.exit_code == 0 else "failed",
        report_path=config.endurance_output_path,
        summary=summarize_endurance(child_report),
    )


def run_artifact_step(
    config: SuiteConfig,
    command_runner: CommandRunner,
) -> dict[str, object]:
    command = [
        sys.executable,
        "tools/subtitle_artifact_validator.py",
        *(str(path) for path in config.artifact_paths),
        "--long-gap-ms",
        str(config.artifact_long_gap_ms),
        "--output",
        str(config.artifact_output_path),
    ]
    if config.artifact_kind:
        command.extend(["--kind", config.artifact_kind])
    remove_existing_report(config.artifact_output_path)
    result = command_runner(command)
    child_report = load_json_report(config.artifact_output_path)
    return build_executed_step(
        name="artifacts",
        command=command,
        result=result,
        status="passed" if result.exit_code == 0 else "failed",
        report_path=config.artifact_output_path,
        summary=summarize_artifacts(child_report),
    )


def build_executed_step(
    *,
    name: str,
    command: list[str],
    result: CommandResult,
    status: str,
    report_path: Path,
    summary: dict[str, object],
) -> dict[str, object]:
    return {
        "name": name,
        "status": status,
        "exit_code": result.exit_code,
        "command": command_for_report(command),
        "report_path": str(report_path),
        "stdout_excerpt": tail_text(result.stdout),
        "stderr_excerpt": tail_text(result.stderr),
        "summary": summary,
    }


def build_skipped_step(*, name: str, reason: str) -> dict[str, object]:
    return {
        "name": name,
        "status": "skipped",
        "exit_code": None,
        "reason": reason,
    }


def build_suite_report(steps: list[dict[str, object]]) -> dict[str, object]:
    status = determine_overall_status(steps)
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": status,
        "steps": steps,
        "next_actions": build_next_actions(steps, status),
    }


def determine_overall_status(steps: list[dict[str, object]]) -> str:
    statuses = [str(step.get("status")) for step in steps]
    executed_statuses = [status for status in statuses if status != "skipped"]
    if any(status == "failed" for status in executed_statuses):
        return "failed"
    if any(status == "blocked" for status in executed_statuses):
        return "blocked"
    if not executed_statuses:
        return "incomplete"
    return "passed"


def build_next_actions(steps: list[dict[str, object]], status: str) -> list[str]:
    actions: list[str] = []
    step_by_name = {str(step.get("name")): step for step in steps}

    preflight = step_by_name.get("preflight")
    if preflight and preflight.get("status") == "blocked":
        blockers = extract_blockers(preflight)
        if blockers:
            actions.append("Resolve preflight blockers: " + "; ".join(blockers))
        else:
            actions.append("Resolve Redis, Whisper, or provider-key preflight blockers.")

    endurance = step_by_name.get("endurance")
    if endurance and endurance.get("status") == "skipped":
        actions.append(
            "Start the backend and rerun with --run-endurance for a 30-60 minute reliability baseline.",
        )
    elif endurance and endurance.get("status") == "failed":
        actions.append(
            "Inspect the endurance stderr excerpt and child report, then rerun after fixing service or threshold failures.",
        )

    artifacts = step_by_name.get("artifacts")
    if artifacts and artifacts.get("status") == "skipped":
        actions.append(
            "Export TXT/SRT/VTT/Markdown from a real session and pass them with --artifact.",
        )
    elif artifacts and artifacts.get("status") == "failed":
        actions.append(
            "Inspect unusable subtitle artifacts and rerun the export or artifact validator.",
        )

    if status == "failed" and not actions:
        actions.append("Inspect failed step stderr excerpts and child report paths.")
    if status == "incomplete":
        actions.append("Run at least preflight, endurance, or artifact validation.")
    return actions


def extract_blockers(step: dict[str, object]) -> list[str]:
    summary = step.get("summary")
    if not isinstance(summary, dict):
        return []
    blockers = summary.get("blockers")
    if not isinstance(blockers, list):
        return []
    return [str(blocker) for blocker in blockers]


def summarize_preflight(report: object) -> dict[str, object]:
    if not isinstance(report, dict):
        return {"report_available": False}
    checks = report.get("checks")
    provider = checks.get("provider") if isinstance(checks, dict) else {}
    whisper = checks.get("whisper") if isinstance(checks, dict) else {}
    redis_check = checks.get("redis") if isinstance(checks, dict) else {}
    return {
        "report_available": True,
        "child_status": report.get("status", ""),
        "blockers": list_value(report.get("blockers")),
        "provider": {
            "engine": mapping_value(provider).get("engine", ""),
            "model": mapping_value(provider).get("model", ""),
            "required_key": mapping_value(provider).get("required_key", ""),
            "key_present": bool(mapping_value(provider).get("key_present", False)),
        },
        "whisper": {
            "engine": mapping_value(whisper).get("engine", ""),
            "package_present": bool(mapping_value(whisper).get("package_present", False)),
            "model": mapping_value(whisper).get("model", ""),
            "device": mapping_value(whisper).get("device", ""),
            "compute_type": mapping_value(whisper).get("compute_type", ""),
            "cuda_available": bool(mapping_value(whisper).get("cuda_available", False)),
            "model_load_checked": bool(mapping_value(whisper).get("model_load_checked", False)),
        },
        "redis": {
            "ok": bool(mapping_value(redis_check).get("ok", False)),
            "url": mapping_value(redis_check).get("url", ""),
            "protocol": mapping_value(redis_check).get("protocol", ""),
            "version": mapping_value(redis_check).get("version", ""),
            "error_type": mapping_value(redis_check).get("error_type", ""),
        },
    }


def summarize_endurance(report: object) -> dict[str, object]:
    if not isinstance(report, dict):
        return {"report_available": False}
    summary = mapping_value(report.get("summary"))
    return {
        "report_available": True,
        "session_id": report.get("session_id", ""),
        "duration_seconds": report.get("duration_seconds", 0),
        "sent_audio_chunks": report.get("sent_audio_chunks", 0),
        "backend_received_ratio": summary.get("backend_received_ratio", 0),
        "backend_audio_chunks_dropped": summary.get("backend_audio_chunks_dropped", 0),
        "backend_audio_queue_max_depth": summary.get("backend_audio_queue_max_depth", 0),
        "reconnect_count": summary.get("reconnect_count", 0),
        "latency": summary.get("latency", {}),
        "subtitle_ordering": summary.get("subtitle_ordering", {}),
        "memory": summary.get("memory", {}),
        "api_call_counts": summary.get("api_call_counts", {}),
        "revision_counts": summary.get("revision_counts", {}),
    }


def summarize_artifacts(report: object) -> dict[str, object]:
    if not isinstance(report, dict):
        return {"report_available": False}
    artifacts = report.get("artifacts")
    unusable_paths: list[str] = []
    if isinstance(artifacts, list):
        for artifact in artifacts:
            if not isinstance(artifact, dict) or artifact.get("is_usable") is True:
                continue
            unusable_paths.append(str(artifact.get("path", "")))
    return {
        "report_available": True,
        "artifact_count": report.get("artifact_count", 0),
        "usable_count": report.get("usable_count", 0),
        "unusable_count": report.get("unusable_count", 0),
        "unusable_paths": unusable_paths,
    }


def mapping_value(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    return {}


def list_value(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def load_json_report(path: Path) -> object:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_report(path: Path, report: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def remove_existing_report(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return


def tail_text(value: str) -> str:
    stripped = value.strip()
    if len(stripped) <= TEXT_EXCERPT_LIMIT:
        return stripped
    return stripped[-TEXT_EXCERPT_LIMIT:]


def command_for_report(command: list[str]) -> list[str]:
    if not command:
        return []
    return [Path(command[0]).name, *command[1:]]


def parse_args(argv: list[str] | None = None) -> SuiteConfig:
    parser = argparse.ArgumentParser(
        description=(
            "Run AI interpreter validation preflight, optional endurance, and "
            "optional subtitle artifact checks into one JSON report."
        ),
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_SUITE_OUTPUT)
    parser.add_argument("--skip-preflight", action="store_true")
    parser.add_argument("--preflight-output", type=Path, default=DEFAULT_PREFLIGHT_OUTPUT)
    parser.add_argument("--load-whisper-model", action="store_true")

    parser.add_argument("--run-endurance", action="store_true")
    parser.add_argument("--endurance-output", type=Path, default=DEFAULT_ENDURANCE_OUTPUT)
    parser.add_argument("--url", default=DEFAULT_WS_URL)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--duration-seconds", type=float, default=None)
    parser.add_argument("--chunk-duration-ms", type=int, default=None)
    parser.add_argument("--sample-rate", type=int, default=None)
    parser.add_argument("--source", choices=["silence", "tone"], default=None)
    parser.add_argument("--wav", type=Path, default=None)
    parser.add_argument("--tone-frequency-hz", type=float, default=None)
    parser.add_argument("--manual-revision-interval-seconds", type=float, default=None)
    parser.add_argument("--receive-timeout-seconds", type=float, default=None)
    parser.add_argument("--max-dropped-chunks", type=int, default=None)
    parser.add_argument("--max-queue-depth", type=int, default=None)
    parser.add_argument("--max-reconnects", type=int, default=None)
    parser.add_argument("--max-latency-ms", type=int, default=None)
    parser.add_argument("--min-received-ratio", type=float, default=None)
    parser.add_argument("--max-subtitle-order-violations", type=int, default=None)
    parser.add_argument("--monitor-self", action="store_true")
    parser.add_argument("--monitor-pid", action="append", default=[])
    parser.add_argument("--memory-sample-interval-seconds", type=float, default=None)
    parser.add_argument("--max-memory-growth-mb", type=float, default=None)

    parser.add_argument("--artifact", action="append", type=Path, default=[])
    parser.add_argument("--artifact-output", type=Path, default=DEFAULT_ARTIFACT_OUTPUT)
    parser.add_argument("--artifact-kind", default=None)
    parser.add_argument("--artifact-long-gap-ms", type=int, default=5000)

    args = parser.parse_args(argv)
    return SuiteConfig(
        output_path=args.output,
        skip_preflight=args.skip_preflight,
        preflight_output_path=args.preflight_output,
        load_whisper_model=args.load_whisper_model,
        run_endurance=args.run_endurance,
        endurance_output_path=args.endurance_output,
        endurance_args=tuple(build_endurance_args(args)),
        artifact_paths=tuple(args.artifact),
        artifact_output_path=args.artifact_output,
        artifact_kind=args.artifact_kind,
        artifact_long_gap_ms=args.artifact_long_gap_ms,
    )


def build_endurance_args(args: argparse.Namespace) -> list[str]:
    values: list[str] = ["--url", str(args.url)]
    add_optional(values, "--session-id", args.session_id)
    add_optional(values, "--duration-seconds", args.duration_seconds)
    add_optional(values, "--chunk-duration-ms", args.chunk_duration_ms)
    add_optional(values, "--sample-rate", args.sample_rate)
    add_optional(values, "--source", args.source)
    add_optional(values, "--wav", args.wav)
    add_optional(values, "--tone-frequency-hz", args.tone_frequency_hz)
    add_optional(
        values,
        "--manual-revision-interval-seconds",
        args.manual_revision_interval_seconds,
    )
    add_optional(values, "--receive-timeout-seconds", args.receive_timeout_seconds)
    add_optional(values, "--max-dropped-chunks", args.max_dropped_chunks)
    add_optional(values, "--max-queue-depth", args.max_queue_depth)
    add_optional(values, "--max-reconnects", args.max_reconnects)
    add_optional(values, "--max-latency-ms", args.max_latency_ms)
    add_optional(values, "--min-received-ratio", args.min_received_ratio)
    add_optional(
        values,
        "--max-subtitle-order-violations",
        args.max_subtitle_order_violations,
    )
    if args.monitor_self:
        values.append("--monitor-self")
    for monitor in args.monitor_pid:
        values.extend(["--monitor-pid", str(monitor)])
    add_optional(
        values,
        "--memory-sample-interval-seconds",
        args.memory_sample_interval_seconds,
    )
    add_optional(values, "--max-memory-growth-mb", args.max_memory_growth_mb)
    return values


def add_optional(values: list[str], flag: str, value: object) -> None:
    if value is None:
        return
    values.extend([flag, str(value)])


def main(argv: list[str] | None = None) -> int:
    try:
        config = parse_args(argv)
        exit_code, report = run_suite(config)
        sys.stdout.write(
            f"Interpreter validation suite report written to {config.output_path}\n",
        )
        if report["status"] != "passed":
            sys.stderr.write(
                f"Interpreter validation suite status: {report['status']}\n",
            )
        return exit_code
    except KeyboardInterrupt:
        sys.stderr.write("Interpreter validation suite interrupted.\n")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
