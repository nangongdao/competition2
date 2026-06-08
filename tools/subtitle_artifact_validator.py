"""Validate subtitle export artifacts from real interpretation sessions."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys


DEFAULT_LONG_GAP_MS = 5000
TIMESTAMP_PATTERN = re.compile(r"^(\d{2,}):(\d{2}):(\d{2})([,.])(\d{3})$")
REVISION_PATTERNS = {
    "asr": re.compile(r"ASR revised|revised:asr_correction", re.IGNORECASE),
    "translation": re.compile(
        r"Translation revised|revised:translation_correction",
        re.IGNORECASE,
    ),
    "generic": re.compile(r"\brevised\b|\[Revised\]", re.IGNORECASE),
}


class ArtifactValidationError(RuntimeError):
    """Raised when an artifact path or format option is invalid."""


@dataclass(frozen=True)
class TimedCue:
    start_ms: int
    end_ms: int
    text: str


def validate_artifact(
    path: Path,
    *,
    kind: str | None = None,
    long_gap_ms: int = DEFAULT_LONG_GAP_MS,
) -> dict[str, object]:
    if not path.exists():
        raise ArtifactValidationError(f"Artifact does not exist: {path}")
    detected_kind = normalize_kind(kind) if kind else detect_kind(path)
    text = path.read_text(encoding="utf-8-sig")
    return validate_artifact_text(
        text,
        kind=detected_kind,
        path_label=str(path),
        long_gap_ms=long_gap_ms,
    )


def validate_artifact_text(
    text: str,
    *,
    kind: str,
    path_label: str = "",
    long_gap_ms: int = DEFAULT_LONG_GAP_MS,
) -> dict[str, object]:
    normalized_kind = normalize_kind(kind)
    text = strip_utf8_bom(text)
    if long_gap_ms < 0:
        raise ArtifactValidationError("Long gap threshold cannot be negative.")

    is_empty = is_effectively_empty(text, normalized_kind)
    revision_markers = count_revision_markers(text)
    warnings: list[str] = []
    if is_empty:
        warnings.append("artifact is empty")

    if normalized_kind in {"srt", "vtt"}:
        timed_summary = validate_timed_subtitles(
            text,
            kind=normalized_kind,
            long_gap_ms=long_gap_ms,
        )
        if timed_summary["invalid_timestamp_count"]:
            warnings.append("invalid subtitle timestamps")
        if timed_summary["overlap_count"]:
            warnings.append("subtitle cues overlap")
        if timed_summary["cue_count"] == 0:
            warnings.append("no subtitle cues")
        is_usable = (
            not is_empty
            and int(timed_summary["cue_count"]) > 0
            and int(timed_summary["invalid_timestamp_count"]) == 0
            and int(timed_summary["overlap_count"]) == 0
        )
        summary: dict[str, object] = timed_summary
    elif normalized_kind == "markdown":
        summary = validate_markdown_notes(text)
        if not summary["has_title"]:
            warnings.append("markdown title is missing")
        if not summary["has_timeline_section"]:
            warnings.append("markdown timeline section is missing")
        if int(summary["timeline_entry_count"]) == 0:
            warnings.append("markdown timeline has no entries")
        is_usable = (
            not is_empty
            and bool(summary["has_title"])
            and bool(summary["has_timeline_section"])
            and int(summary["timeline_entry_count"]) > 0
        )
    else:
        summary = validate_plain_transcript(text)
        if int(summary["entry_count"]) == 0:
            warnings.append("plain transcript has no numbered entries")
        is_usable = not is_empty and int(summary["entry_count"]) > 0

    return {
        "path": path_label,
        "kind": normalized_kind,
        "is_empty": is_empty,
        "is_usable": is_usable,
        "warnings": warnings,
        "revision_markers": revision_markers,
        "summary": summary,
    }


def validate_timed_subtitles(
    text: str,
    *,
    kind: str,
    long_gap_ms: int,
) -> dict[str, object]:
    cues, invalid_timestamp_count = parse_timed_cues(text)
    overlap_count = 0
    gap_count = 0
    long_gap_count = 0
    max_gap_ms = 0
    previous_end_ms: int | None = None

    for cue in cues:
        if previous_end_ms is not None:
            if cue.start_ms < previous_end_ms:
                overlap_count += 1
            elif cue.start_ms > previous_end_ms:
                gap_ms = cue.start_ms - previous_end_ms
                gap_count += 1
                max_gap_ms = max(max_gap_ms, gap_ms)
                if gap_ms > long_gap_ms:
                    long_gap_count += 1
        previous_end_ms = max(previous_end_ms or 0, cue.end_ms)

    return {
        "format": kind,
        "cue_count": len(cues),
        "invalid_timestamp_count": invalid_timestamp_count,
        "overlap_count": overlap_count,
        "gap_count": gap_count,
        "long_gap_count": long_gap_count,
        "max_gap_ms": max_gap_ms,
        "duration_ms": cues[-1].end_ms if cues else 0,
        "empty_cue_count": sum(1 for cue in cues if not cue.text.strip()),
    }


def validate_plain_transcript(text: str) -> dict[str, object]:
    lines = text.splitlines()
    return {
        "line_count": len(lines),
        "entry_count": sum(1 for line in lines if re.match(r"^\d+\.\s", line)),
        "source_line_count": sum(1 for line in lines if line.startswith("EN:")),
        "translation_line_count": sum(1 for line in lines if line.startswith("ZH:")),
    }


def validate_markdown_notes(text: str) -> dict[str, object]:
    lines = text.splitlines()
    heading_count = sum(1 for line in lines if line.startswith("#"))
    bullet_count = sum(1 for line in lines if line.startswith("- "))
    return {
        "line_count": len(lines),
        "heading_count": heading_count,
        "bullet_count": bullet_count,
        "has_title": any(line.startswith("# ") for line in lines),
        "has_timeline_section": any(line.strip() == "## Timeline" for line in lines),
        "timeline_entry_count": sum(1 for line in lines if re.match(r"^###\s+\d+\.", line)),
        "source_line_count": sum(1 for line in lines if line.startswith("- Source:")),
        "translation_line_count": sum(1 for line in lines if line.startswith("- Translation:")),
    }


def parse_timed_cues(text: str) -> tuple[list[TimedCue], int]:
    cues: list[TimedCue] = []
    invalid_timestamp_count = 0
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if "-->" not in line:
            index += 1
            continue

        start_text, end_text = split_timestamp_line(line)
        start_ms = parse_timestamp_ms(start_text)
        end_ms = parse_timestamp_ms(end_text)
        if start_ms is None or end_ms is None or end_ms <= start_ms:
            invalid_timestamp_count += 1
            index += 1
            continue

        text_lines: list[str] = []
        index += 1
        while index < len(lines) and lines[index].strip():
            text_lines.append(lines[index].strip())
            index += 1
        cues.append(TimedCue(start_ms=start_ms, end_ms=end_ms, text="\n".join(text_lines)))
    return cues, invalid_timestamp_count


def split_timestamp_line(line: str) -> tuple[str, str]:
    start_text, raw_end_text = line.split("-->", 1)
    end_text = raw_end_text.strip().split()[0]
    return start_text.strip(), end_text.strip()


def parse_timestamp_ms(value: str) -> int | None:
    match = TIMESTAMP_PATTERN.match(value)
    if not match:
        return None
    hours, minutes, seconds, _separator, milliseconds = match.groups()
    return (
        int(hours) * 3_600_000
        + int(minutes) * 60_000
        + int(seconds) * 1000
        + int(milliseconds)
    )


def count_revision_markers(text: str) -> dict[str, int]:
    counts = {
        "asr": len(REVISION_PATTERNS["asr"].findall(text)),
        "translation": len(REVISION_PATTERNS["translation"].findall(text)),
    }
    generic_count = len(REVISION_PATTERNS["generic"].findall(text))
    counts["generic"] = max(0, generic_count - counts["asr"] - counts["translation"])
    counts["total"] = counts["asr"] + counts["translation"] + counts["generic"]
    return counts


def is_effectively_empty(text: str, kind: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if kind == "vtt" and stripped == "WEBVTT":
        return True
    return False


def strip_utf8_bom(text: str) -> str:
    if text.startswith("\ufeff"):
        return text[1:]
    return text


def detect_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".srt":
        return "srt"
    if suffix == ".vtt":
        return "vtt"
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix == ".txt":
        return "txt"
    raise ArtifactValidationError(f"Unsupported artifact extension: {path.suffix}")


def normalize_kind(kind: str) -> str:
    normalized = kind.lower()
    if normalized in {"md", "markdown"}:
        return "markdown"
    if normalized in {"txt", "text", "transcript"}:
        return "txt"
    if normalized in {"srt", "vtt"}:
        return normalized
    raise ArtifactValidationError(f"Unsupported artifact kind: {kind}")


def build_validation_report(
    paths: list[Path],
    *,
    kind: str | None,
    long_gap_ms: int,
) -> dict[str, object]:
    artifacts = [
        validate_artifact(path, kind=kind, long_gap_ms=long_gap_ms)
        for path in paths
    ]
    usable_count = sum(1 for artifact in artifacts if artifact["is_usable"])
    return {
        "artifact_count": len(artifacts),
        "usable_count": usable_count,
        "unusable_count": len(artifacts) - usable_count,
        "artifacts": artifacts,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate subtitle export artifacts from a real session.",
    )
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--kind", default=None, help="Override artifact kind for all paths.")
    parser.add_argument("--long-gap-ms", type=int, default=DEFAULT_LONG_GAP_MS)
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        report = build_validation_report(
            args.paths,
            kind=args.kind,
            long_gap_ms=args.long_gap_ms,
        )
        payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload, encoding="utf-8")
        else:
            sys.stdout.write(payload)
        return 0 if report["unusable_count"] == 0 else 2
    except ArtifactValidationError as exc:
        sys.stderr.write(f"Artifact validation failed: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
