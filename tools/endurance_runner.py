"""WebSocket endurance runner for live interpretation diagnostics.

The runner behaves like a lightweight browser audio client: it opens the live
translation WebSocket, sends 16 kHz mono float32 PCM chunks at a fixed cadence,
listens for server messages, and writes a JSON report that can be compared
between long runs.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import time
from typing import TypeVar
import uuid
import wave

import websockets
from websockets.exceptions import ConnectionClosed


DEFAULT_WS_URL = "ws://localhost:8000/api/v1/ws/translate"
DEFAULT_DURATION_SECONDS = 60
DEFAULT_CHUNK_DURATION_MS = 100
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_RECEIVE_TIMEOUT_SECONDS = 2.0
DEFAULT_OUTPUT_PATH = Path("reports/endurance-latest.json")
MANUAL_REVISE_MESSAGE = json.dumps({"type": "manual_revise"})
REQUEST_DIAGNOSTICS_MESSAGE = json.dumps({"type": "request_diagnostics"})
SampleT = TypeVar("SampleT")


class EnduranceRunnerError(RuntimeError):
    """Raised for invalid runner configuration or failed validation."""


@dataclass(frozen=True)
class Thresholds:
    max_dropped_chunks: int | None
    max_queue_depth: int | None
    max_reconnects: int | None
    max_latency_ms: int | None
    min_received_ratio: float | None
    max_subtitle_order_violations: int | None = None
    max_memory_growth_mb: float | None = None


@dataclass(frozen=True)
class MemoryMonitorSpec:
    label: str
    pid: int


@dataclass(frozen=True)
class RunnerConfig:
    ws_url: str
    session_id: str
    duration_seconds: float
    chunk_duration_ms: int
    sample_rate: int
    source: str
    wav_path: Path | None
    tone_frequency_hz: float
    manual_revision_interval_seconds: float
    receive_timeout_seconds: float
    output_path: Path
    thresholds: Thresholds
    memory_monitors: tuple[MemoryMonitorSpec, ...] = ()
    memory_sample_interval_seconds: float = 5.0


@dataclass
class RunnerState:
    sent_audio_chunks: int = 0
    sent_audio_bytes: int = 0
    manual_revision_requests: int = 0
    received_message_counts: Counter[str] = field(default_factory=Counter)
    status_codes: Counter[str] = field(default_factory=Counter)
    errors: list[dict[str, str]] = field(default_factory=list)
    latest_diagnostics: dict[str, object] | None = None
    first_message_at: float | None = None
    last_message_at: float | None = None
    translation_final_messages: int = 0
    finalized_segment_ids: set[str] = field(default_factory=set)
    duplicate_final_segments: int = 0
    duplicate_final_segment_ids: list[str] = field(default_factory=list)
    out_of_order_final_segments: int = 0
    out_of_order_final_segment_ids: list[str] = field(default_factory=list)
    final_sequence_gap_events: int = 0
    missing_final_segment_estimate: int = 0
    final_sequence_gap_samples: list[dict[str, object]] = field(default_factory=list)
    unparseable_final_segments: int = 0
    unparseable_final_segment_ids: list[str] = field(default_factory=list)
    revisions_for_unknown_segments: int = 0
    unknown_revision_segment_ids: list[str] = field(default_factory=list)
    last_final_sequence: int | None = None
    memory_samples: list[dict[str, object]] = field(default_factory=list)


class GeneratedAudioSource:
    """Generate deterministic float32 PCM chunks."""

    def __init__(
        self,
        *,
        source: str,
        sample_rate: int,
        chunk_duration_ms: int,
        tone_frequency_hz: float,
    ) -> None:
        self.label = source
        frame_count = frames_per_chunk(sample_rate, chunk_duration_ms)
        if source == "silence":
            self._chunk = b"\x00" * frame_count * 4
        elif source == "tone":
            self._chunk = float32_bytes(
                math.sin(2 * math.pi * tone_frequency_hz * index / sample_rate) * 0.2
                for index in range(frame_count)
            )
        else:
            raise EnduranceRunnerError(f"Unsupported generated source: {source}")

    def next_chunk(self) -> bytes:
        return self._chunk

    def close(self) -> None:
        return


class WavAudioSource:
    """Read a 16 kHz mono PCM WAV file and loop it until the run ends."""

    def __init__(
        self,
        *,
        wav_path: Path,
        sample_rate: int,
        chunk_duration_ms: int,
    ) -> None:
        if not wav_path.exists():
            raise EnduranceRunnerError(f"WAV file does not exist: {wav_path}")

        self.label = f"wav:{wav_path}"
        self._wav = wave.open(str(wav_path), "rb")
        self._frames_per_chunk = frames_per_chunk(sample_rate, chunk_duration_ms)
        self._sample_width = self._wav.getsampwidth()

        if self._wav.getnchannels() != 1:
            self.close()
            raise EnduranceRunnerError("WAV input must be mono.")
        if self._wav.getframerate() != sample_rate:
            self.close()
            raise EnduranceRunnerError(f"WAV input must be {sample_rate} Hz.")
        if self._sample_width not in {1, 2, 4}:
            self.close()
            raise EnduranceRunnerError("WAV input must use 8-bit, 16-bit, or 32-bit PCM.")

    def next_chunk(self) -> bytes:
        frames = self._wav.readframes(self._frames_per_chunk)
        if not frames:
            self._wav.rewind()
            frames = self._wav.readframes(self._frames_per_chunk)

        if not frames:
            raise EnduranceRunnerError("WAV input is empty.")

        return pcm_frames_to_float32_bytes(frames, self._sample_width)

    def close(self) -> None:
        self._wav.close()


def frames_per_chunk(sample_rate: int, chunk_duration_ms: int) -> int:
    if sample_rate <= 0:
        raise EnduranceRunnerError("Sample rate must be positive.")
    if chunk_duration_ms <= 0:
        raise EnduranceRunnerError("Chunk duration must be positive.")
    return max(1, round(sample_rate * chunk_duration_ms / 1000))


def float32_bytes(samples: Iterable[float]) -> bytes:
    values = list(samples)
    if not values:
        return b""
    return struct.pack(f"<{len(values)}f", *values)


def pcm_frames_to_float32_bytes(frames: bytes, sample_width: int) -> bytes:
    if sample_width == 1:
        return float32_bytes((sample - 128) / 128 for sample in frames)
    if sample_width == 2:
        return float32_bytes(
            sample[0] / 32768
            for sample in struct.iter_unpack("<h", frames)
        )
    if sample_width == 4:
        return float32_bytes(
            sample[0] / 2147483648
            for sample in struct.iter_unpack("<i", frames)
        )
    raise EnduranceRunnerError(f"Unsupported PCM sample width: {sample_width}")


def build_session_url(ws_url: str, session_id: str) -> str:
    normalized = ws_url.rstrip("/")
    if normalized.endswith("/ws/translate"):
        return f"{normalized}/{session_id}"
    return normalized


def parse_json_message(raw_message: str | bytes) -> dict[str, object] | None:
    if isinstance(raw_message, bytes):
        return None
    try:
        parsed = json.loads(raw_message)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None


def record_message(state: RunnerState, message: dict[str, object]) -> None:
    now = time.time()
    if state.first_message_at is None:
        state.first_message_at = now
    state.last_message_at = now

    message_type = message.get("type")
    if isinstance(message_type, str):
        state.received_message_counts[message_type] += 1

    if message_type == "status":
        code = message.get("code")
        if isinstance(code, str):
            state.status_codes[code] += 1

    if message_type == "error":
        state.errors.append({
            "code": str(message.get("code", "")),
            "message": str(message.get("message", "")),
        })

    if message_type == "session_diagnostics":
        diagnostics = message.get("diagnostics")
        if isinstance(diagnostics, dict):
            state.latest_diagnostics = diagnostics

    if message_type == "translation_token" and message.get("is_final") is True:
        segment_id = message.get("segment_id")
        if isinstance(segment_id, str):
            record_final_translation_segment(state, segment_id)

    if message_type == "revision":
        segment_id = message.get("segment_id")
        if isinstance(segment_id, str) and segment_id not in state.finalized_segment_ids:
            state.revisions_for_unknown_segments += 1
            append_sample(state.unknown_revision_segment_ids, segment_id)


def record_final_translation_segment(state: RunnerState, segment_id: str) -> None:
    state.translation_final_messages += 1
    if segment_id in state.finalized_segment_ids:
        state.duplicate_final_segments += 1
        append_sample(state.duplicate_final_segment_ids, segment_id)
        return

    state.finalized_segment_ids.add(segment_id)
    sequence = segment_sequence(segment_id)
    if sequence is None:
        state.unparseable_final_segments += 1
        append_sample(state.unparseable_final_segment_ids, segment_id)
        return

    previous_sequence = state.last_final_sequence
    if previous_sequence is not None:
        if sequence <= previous_sequence:
            state.out_of_order_final_segments += 1
            append_sample(state.out_of_order_final_segment_ids, segment_id)
        elif sequence > previous_sequence + 1:
            missing_count = sequence - previous_sequence - 1
            state.final_sequence_gap_events += 1
            state.missing_final_segment_estimate += missing_count
            append_sample(
                state.final_sequence_gap_samples,
                {
                    "previous_sequence": previous_sequence,
                    "current_sequence": sequence,
                    "missing_count": missing_count,
                    "segment_id": segment_id,
                },
            )

    if previous_sequence is None or sequence > previous_sequence:
        state.last_final_sequence = sequence


def segment_sequence(segment_id: str) -> int | None:
    _prefix, separator, suffix = segment_id.rpartition("_")
    if not separator or not suffix.isdigit():
        return None
    return int(suffix)


def append_sample(samples: list[SampleT], value: SampleT, *, limit: int = 20) -> None:
    if len(samples) < limit:
        samples.append(value)


def record_memory_samples(
    state: RunnerState,
    monitors: tuple[MemoryMonitorSpec, ...],
    started_at: float,
) -> None:
    if not monitors:
        return

    now = time.time()
    for monitor in monitors:
        rss_bytes, error = read_process_rss_bytes(monitor.pid)
        sample: dict[str, object] = {
            "label": monitor.label,
            "pid": monitor.pid,
            "timestamp": now,
            "elapsed_seconds": round(now - started_at, 3),
        }
        if rss_bytes is None:
            sample["error"] = error or "RSS unavailable"
        else:
            sample["rss_mb"] = round(rss_bytes / 1024 / 1024, 3)
        state.memory_samples.append(sample)


def read_process_rss_bytes(pid: int) -> tuple[int | None, str | None]:
    if pid <= 0:
        return None, "PID must be positive"
    if sys.platform == "win32":
        return read_windows_process_rss_bytes(pid)
    if sys.platform.startswith("linux"):
        return read_linux_process_rss_bytes(pid)
    return read_ps_process_rss_bytes(pid)


def read_linux_process_rss_bytes(pid: int) -> tuple[int | None, str | None]:
    status_path = Path("/proc") / str(pid) / "status"
    try:
        for line in status_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                parts = line.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    return int(parts[1]) * 1024, None
                return None, f"Unable to parse VmRSS from {status_path}"
    except OSError as exc:
        return None, f"{type(exc).__name__}: {exc}"
    return None, f"VmRSS not found in {status_path}"


def read_ps_process_rss_bytes(pid: int) -> tuple[int | None, str | None]:
    try:
        result = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(pid)],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"{type(exc).__name__}: {exc}"

    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "ps failed"
        return None, message

    value = result.stdout.strip()
    if not value or not value.split()[0].isdigit():
        return None, f"Unable to parse RSS from ps output: {value!r}"
    return int(value.split()[0]) * 1024, None


def read_windows_process_rss_bytes(pid: int) -> tuple[int | None, str | None]:
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError as exc:
        return None, f"{type(exc).__name__}: {exc}"

    class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
            ("PrivateUsage", ctypes.c_size_t),
        ]

    process_query_limited_information = 0x1000
    process_vm_read = 0x0010
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(PROCESS_MEMORY_COUNTERS_EX),
        wintypes.DWORD,
    ]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(
        process_query_limited_information | process_vm_read,
        False,
        pid,
    )
    if not handle:
        return None, f"OpenProcess failed: {ctypes.get_last_error()}"

    try:
        counters = PROCESS_MEMORY_COUNTERS_EX()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX)
        ok = psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
        if not ok:
            return None, f"GetProcessMemoryInfo failed: {ctypes.get_last_error()}"
        return int(counters.WorkingSetSize), None
    finally:
        kernel32.CloseHandle(handle)


async def receive_messages(websocket, state: RunnerState, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            raw_message = await asyncio.wait_for(websocket.recv(), timeout=0.5)
        except TimeoutError:
            continue
        except ConnectionClosed:
            stop_event.set()
            return

        message = parse_json_message(raw_message)
        if message:
            record_message(state, message)


async def send_audio(
    websocket,
    *,
    config: RunnerConfig,
    source: GeneratedAudioSource | WavAudioSource,
    state: RunnerState,
    stop_event: asyncio.Event,
) -> None:
    loop = asyncio.get_running_loop()
    started_at = loop.time()
    next_chunk_at = started_at
    next_manual_revision_at = (
        started_at + config.manual_revision_interval_seconds
        if config.manual_revision_interval_seconds > 0
        else math.inf
    )

    while not stop_event.is_set():
        now = loop.time()
        if now - started_at >= config.duration_seconds:
            return

        chunk = source.next_chunk()
        try:
            await websocket.send(chunk)
        except ConnectionClosed:
            stop_event.set()
            return
        state.sent_audio_chunks += 1
        state.sent_audio_bytes += len(chunk)

        now = loop.time()
        if now >= next_manual_revision_at:
            try:
                await websocket.send(MANUAL_REVISE_MESSAGE)
            except ConnectionClosed:
                stop_event.set()
                return
            state.manual_revision_requests += 1
            next_manual_revision_at = now + config.manual_revision_interval_seconds

        next_chunk_at += config.chunk_duration_ms / 1000
        await asyncio.sleep(max(0, next_chunk_at - loop.time()))


async def sample_memory(
    *,
    config: RunnerConfig,
    state: RunnerState,
    started_at: float,
    stop_event: asyncio.Event,
) -> None:
    record_memory_samples(state, config.memory_monitors, started_at)
    while not stop_event.is_set():
        await asyncio.sleep(config.memory_sample_interval_seconds)
        record_memory_samples(state, config.memory_monitors, started_at)


async def run_endurance(config: RunnerConfig) -> dict[str, object]:
    state = RunnerState()
    source = create_audio_source(config)
    url = build_session_url(config.ws_url, config.session_id)
    started_at = time.time()
    stop_event = asyncio.Event()
    memory_task: asyncio.Task[None] | None = None

    try:
        if config.memory_monitors:
            memory_task = asyncio.create_task(sample_memory(
                config=config,
                state=state,
                started_at=started_at,
                stop_event=stop_event,
            ))
        async with websockets.connect(url, max_size=None) as websocket:
            receiver_task = asyncio.create_task(receive_messages(websocket, state, stop_event))
            sender_task = asyncio.create_task(send_audio(
                websocket,
                config=config,
                source=source,
                state=state,
                stop_event=stop_event,
            ))

            await sender_task
            if not stop_event.is_set():
                try:
                    await websocket.send(REQUEST_DIAGNOSTICS_MESSAGE)
                except ConnectionClosed:
                    stop_event.set()
            try:
                await asyncio.wait_for(receiver_task, timeout=config.receive_timeout_seconds)
            except TimeoutError:
                stop_event.set()
                receiver_task.cancel()
                await asyncio.gather(receiver_task, return_exceptions=True)
    finally:
        if memory_task is not None:
            stop_event.set()
            memory_task.cancel()
            await asyncio.gather(memory_task, return_exceptions=True)
            record_memory_samples(state, config.memory_monitors, started_at)
        source.close()

    ended_at = time.time()
    report = build_report(
        config=config,
        url=url,
        state=state,
        started_at=started_at,
        ended_at=ended_at,
    )
    validate_thresholds(report, config.thresholds)
    return report


def create_audio_source(config: RunnerConfig) -> GeneratedAudioSource | WavAudioSource:
    if config.wav_path:
        return WavAudioSource(
            wav_path=config.wav_path,
            sample_rate=config.sample_rate,
            chunk_duration_ms=config.chunk_duration_ms,
        )
    return GeneratedAudioSource(
        source=config.source,
        sample_rate=config.sample_rate,
        chunk_duration_ms=config.chunk_duration_ms,
        tone_frequency_hz=config.tone_frequency_hz,
    )


def build_report(
    *,
    config: RunnerConfig,
    url: str,
    state: RunnerState,
    started_at: float,
    ended_at: float,
) -> dict[str, object]:
    diagnostics = state.latest_diagnostics or {}
    return {
        "session_id": config.session_id,
        "url": url,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_seconds": round(ended_at - started_at, 3),
        "audio_source": f"wav:{config.wav_path}" if config.wav_path else config.source,
        "sample_rate": config.sample_rate,
        "chunk_duration_ms": config.chunk_duration_ms,
        "sent_audio_chunks": state.sent_audio_chunks,
        "sent_audio_bytes": state.sent_audio_bytes,
        "manual_revision_requests": state.manual_revision_requests,
        "received_message_counts": dict(sorted(state.received_message_counts.items())),
        "status_codes": dict(sorted(state.status_codes.items())),
        "errors": state.errors,
        "memory_samples": state.memory_samples,
        "latest_diagnostics": diagnostics,
        "summary": {
            "backend_audio_chunks_received": int_value(diagnostics.get("audio_chunks_received")),
            "backend_audio_chunks_dropped": int_value(diagnostics.get("audio_chunks_dropped")),
            "backend_audio_bytes_received": int_value(diagnostics.get("audio_bytes_received")),
            "backend_audio_queue_depth": int_value(diagnostics.get("audio_queue_depth")),
            "backend_audio_queue_max_depth": int_value(diagnostics.get("audio_queue_max_depth")),
            "backend_audio_queue_capacity": int_value(diagnostics.get("audio_queue_capacity")),
            "backend_received_ratio": received_ratio(
                sent_audio_chunks=state.sent_audio_chunks,
                backend_audio_chunks_received=int_value(diagnostics.get("audio_chunks_received")),
            ),
            "asr_segments": int_value(diagnostics.get("asr_segments")),
            "translation_segments": int_value(diagnostics.get("translation_segments")),
            "revision_segments": int_value(diagnostics.get("revision_segments")),
            "reconnect_count": int_value(diagnostics.get("reconnect_count")),
            "latency": diagnostics.get("latency", {}),
            "api_call_counts": numeric_mapping(diagnostics.get("api_call_counts")),
            "revision_counts": numeric_mapping(diagnostics.get("revision_counts")),
            "revision_sources": numeric_mapping(diagnostics.get("revision_sources")),
            "revision_triggers": numeric_mapping(diagnostics.get("revision_triggers")),
            "subtitle_ordering": build_subtitle_ordering_summary(state),
            "memory": build_memory_summary(state.memory_samples),
        },
    }


def int_value(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return 0


def received_ratio(
    *,
    sent_audio_chunks: int,
    backend_audio_chunks_received: int,
) -> float:
    if sent_audio_chunks <= 0:
        return 0.0
    return round(backend_audio_chunks_received / sent_audio_chunks, 4)


def float_value(value: object) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def numeric_mapping(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key, item in value.items():
        if isinstance(key, str):
            result[key] = int_value(item)
    return dict(sorted(result.items()))


def build_memory_summary(samples: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for sample in samples:
        label = sample.get("label")
        if isinstance(label, str):
            grouped.setdefault(label, []).append(sample)

    summary: dict[str, dict[str, object]] = {}
    for label, label_samples in sorted(grouped.items()):
        rss_values = [
            float_value(sample.get("rss_mb"))
            for sample in label_samples
            if isinstance(sample.get("rss_mb"), int | float)
        ]
        errors = [
            str(sample.get("error"))
            for sample in label_samples
            if isinstance(sample.get("error"), str)
        ]
        pids = [
            int_value(sample.get("pid"))
            for sample in label_samples
            if isinstance(sample.get("pid"), int)
        ]
        latest_pid = pids[-1] if pids else 0
        if not rss_values:
            summary[label] = {
                "pid": latest_pid,
                "sample_count": 0,
                "unavailable_samples": len(errors),
                "errors": errors[:5],
            }
            continue

        start_rss_mb = rss_values[0]
        end_rss_mb = rss_values[-1]
        peak_rss_mb = max(rss_values)
        summary[label] = {
            "pid": latest_pid,
            "sample_count": len(rss_values),
            "unavailable_samples": len(errors),
            "start_rss_mb": round(start_rss_mb, 3),
            "end_rss_mb": round(end_rss_mb, 3),
            "peak_rss_mb": round(peak_rss_mb, 3),
            "growth_mb": round(end_rss_mb - start_rss_mb, 3),
            "peak_growth_mb": round(peak_rss_mb - start_rss_mb, 3),
        }
        if errors:
            summary[label]["errors"] = errors[:5]

    return summary


def build_subtitle_ordering_summary(state: RunnerState) -> dict[str, object]:
    order_violation_count = (
        state.duplicate_final_segments
        + state.out_of_order_final_segments
        + state.final_sequence_gap_events
        + state.revisions_for_unknown_segments
    )
    return {
        "translation_final_messages": state.translation_final_messages,
        "unique_final_segments": len(state.finalized_segment_ids),
        "order_violation_count": order_violation_count,
        "duplicate_final_segments": state.duplicate_final_segments,
        "duplicate_final_segment_ids": state.duplicate_final_segment_ids,
        "out_of_order_final_segments": state.out_of_order_final_segments,
        "out_of_order_final_segment_ids": state.out_of_order_final_segment_ids,
        "final_sequence_gap_events": state.final_sequence_gap_events,
        "missing_final_segment_estimate": state.missing_final_segment_estimate,
        "final_sequence_gap_samples": state.final_sequence_gap_samples,
        "revisions_for_unknown_segments": state.revisions_for_unknown_segments,
        "unknown_revision_segment_ids": state.unknown_revision_segment_ids,
        "unparseable_final_segments": state.unparseable_final_segments,
        "unparseable_final_segment_ids": state.unparseable_final_segment_ids,
    }


def validate_thresholds(report: dict[str, object], thresholds: Thresholds) -> None:
    summary = report.get("summary")
    if not isinstance(summary, dict):
        return

    failures: list[str] = []
    dropped_chunks = int_value(summary.get("backend_audio_chunks_dropped"))
    queue_max_depth = int_value(summary.get("backend_audio_queue_max_depth"))
    reconnect_count = int_value(summary.get("reconnect_count"))
    backend_received_ratio = float_value(summary.get("backend_received_ratio"))

    if thresholds.max_dropped_chunks is not None and dropped_chunks > thresholds.max_dropped_chunks:
        failures.append(
            f"dropped chunks {dropped_chunks} > {thresholds.max_dropped_chunks}",
        )
    if thresholds.max_queue_depth is not None and queue_max_depth > thresholds.max_queue_depth:
        failures.append(
            f"audio queue max depth {queue_max_depth} > {thresholds.max_queue_depth}",
        )
    if thresholds.max_reconnects is not None and reconnect_count > thresholds.max_reconnects:
        failures.append(f"reconnects {reconnect_count} > {thresholds.max_reconnects}")
    if (
        thresholds.min_received_ratio is not None
        and backend_received_ratio < thresholds.min_received_ratio
    ):
        failures.append(
            f"received ratio {backend_received_ratio:.4f} < {thresholds.min_received_ratio:.4f}",
        )

    if thresholds.max_latency_ms is not None:
        latency = summary.get("latency")
        if isinstance(latency, dict):
            for name, value in latency.items():
                if not isinstance(value, dict):
                    continue
                avg_ms = int_value(value.get("avg_ms"))
                if avg_ms > thresholds.max_latency_ms:
                    failures.append(f"{name} avg {avg_ms}ms > {thresholds.max_latency_ms}ms")

    if thresholds.max_subtitle_order_violations is not None:
        subtitle_ordering = summary.get("subtitle_ordering")
        if isinstance(subtitle_ordering, dict):
            order_violations = int_value(subtitle_ordering.get("order_violation_count"))
            if order_violations > thresholds.max_subtitle_order_violations:
                failures.append(
                    "subtitle order violations "
                    f"{order_violations} > {thresholds.max_subtitle_order_violations}",
                )

    if thresholds.max_memory_growth_mb is not None:
        memory = summary.get("memory")
        if isinstance(memory, dict):
            for label, value in memory.items():
                if not isinstance(label, str) or not isinstance(value, dict):
                    continue
                growth_mb = float_value(value.get("growth_mb"))
                if growth_mb > thresholds.max_memory_growth_mb:
                    failures.append(
                        f"{label} memory growth "
                        f"{growth_mb:.3f}MB > {thresholds.max_memory_growth_mb:.3f}MB",
                    )

    if failures:
        raise EnduranceRunnerError("; ".join(failures))


def write_report(path: Path, report: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def parse_memory_monitor(value: str) -> MemoryMonitorSpec:
    label = ""
    pid_text = value
    if "=" in value:
        label, pid_text = value.split("=", 1)
        label = label.strip()
    pid_text = pid_text.strip()
    if not pid_text.isdigit():
        raise argparse.ArgumentTypeError(
            "Memory monitor must be a PID or label=PID.",
        )
    pid = int(pid_text)
    if pid <= 0:
        raise argparse.ArgumentTypeError("Memory monitor PID must be positive.")
    return MemoryMonitorSpec(label=label or f"pid-{pid}", pid=pid)


def parse_args(argv: list[str] | None = None) -> RunnerConfig:
    parser = argparse.ArgumentParser(
        description="Run a WebSocket audio endurance session and write diagnostics JSON.",
    )
    parser.add_argument("--url", default=DEFAULT_WS_URL, help="Base or session WebSocket URL.")
    parser.add_argument("--session-id", default=str(uuid.uuid4())[:8], help="Session ID to use.")
    parser.add_argument("--duration-seconds", type=float, default=DEFAULT_DURATION_SECONDS)
    parser.add_argument("--chunk-duration-ms", type=int, default=DEFAULT_CHUNK_DURATION_MS)
    parser.add_argument("--sample-rate", type=int, default=DEFAULT_SAMPLE_RATE)
    parser.add_argument("--source", choices=["silence", "tone"], default="silence")
    parser.add_argument("--wav", type=Path, default=None, help="Optional 16 kHz mono PCM WAV input.")
    parser.add_argument("--tone-frequency-hz", type=float, default=440.0)
    parser.add_argument(
        "--manual-revision-interval-seconds",
        type=float,
        default=0.0,
        help="Send manual revision control messages at this interval; 0 disables it.",
    )
    parser.add_argument(
        "--receive-timeout-seconds",
        type=float,
        default=DEFAULT_RECEIVE_TIMEOUT_SECONDS,
        help="How long to wait for final diagnostics after sending stops.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--max-dropped-chunks", type=int, default=None)
    parser.add_argument(
        "--max-queue-depth",
        type=int,
        default=None,
        help="Fail if backend audio queue max depth exceeds this value.",
    )
    parser.add_argument("--max-reconnects", type=int, default=None)
    parser.add_argument("--max-latency-ms", type=int, default=None)
    parser.add_argument(
        "--max-subtitle-order-violations",
        type=int,
        default=None,
        help=(
            "Fail if final subtitle ordering shows more duplicate, out-of-order, "
            "gap, or unknown-revision events than this value."
        ),
    )
    parser.add_argument(
        "--min-received-ratio",
        type=float,
        default=None,
        help="Fail if backend received / client sent audio chunk ratio is below this value.",
    )
    parser.add_argument(
        "--monitor-self",
        action="store_true",
        help="Sample RSS memory for the endurance runner process itself.",
    )
    parser.add_argument(
        "--monitor-pid",
        action="append",
        type=parse_memory_monitor,
        default=[],
        metavar="LABEL=PID",
        help="Sample RSS memory for a process PID; may be repeated.",
    )
    parser.add_argument(
        "--memory-sample-interval-seconds",
        type=float,
        default=5.0,
        help="Seconds between process memory samples when monitoring is enabled.",
    )
    parser.add_argument(
        "--max-memory-growth-mb",
        type=float,
        default=None,
        help="Fail if any monitored process RSS growth exceeds this value.",
    )

    args = parser.parse_args(argv)
    if args.duration_seconds <= 0:
        raise EnduranceRunnerError("Duration must be positive.")
    if args.manual_revision_interval_seconds < 0:
        raise EnduranceRunnerError("Manual revision interval cannot be negative.")
    if args.max_queue_depth is not None and args.max_queue_depth < 0:
        raise EnduranceRunnerError("Maximum queue depth cannot be negative.")
    if (
        args.max_subtitle_order_violations is not None
        and args.max_subtitle_order_violations < 0
    ):
        raise EnduranceRunnerError("Maximum subtitle order violations cannot be negative.")
    if args.min_received_ratio is not None and not 0 <= args.min_received_ratio <= 1:
        raise EnduranceRunnerError("Minimum received ratio must be between 0 and 1.")
    if args.memory_sample_interval_seconds <= 0:
        raise EnduranceRunnerError("Memory sample interval must be positive.")
    if args.max_memory_growth_mb is not None and args.max_memory_growth_mb < 0:
        raise EnduranceRunnerError("Maximum memory growth cannot be negative.")

    memory_monitors = list(args.monitor_pid)
    if args.monitor_self:
        memory_monitors.insert(0, MemoryMonitorSpec(label="runner", pid=os.getpid()))

    return RunnerConfig(
        ws_url=args.url,
        session_id=args.session_id,
        duration_seconds=args.duration_seconds,
        chunk_duration_ms=args.chunk_duration_ms,
        sample_rate=args.sample_rate,
        source=args.source,
        wav_path=args.wav,
        tone_frequency_hz=args.tone_frequency_hz,
        manual_revision_interval_seconds=args.manual_revision_interval_seconds,
        receive_timeout_seconds=args.receive_timeout_seconds,
        output_path=args.output,
        thresholds=Thresholds(
            max_dropped_chunks=args.max_dropped_chunks,
            max_queue_depth=args.max_queue_depth,
            max_reconnects=args.max_reconnects,
            max_latency_ms=args.max_latency_ms,
            min_received_ratio=args.min_received_ratio,
            max_subtitle_order_violations=args.max_subtitle_order_violations,
            max_memory_growth_mb=args.max_memory_growth_mb,
        ),
        memory_monitors=tuple(memory_monitors),
        memory_sample_interval_seconds=args.memory_sample_interval_seconds,
    )


async def async_main(argv: list[str] | None = None) -> int:
    config = parse_args(argv)
    report = await run_endurance(config)
    write_report(config.output_path, report)
    sys.stdout.write(f"Endurance report written to {config.output_path}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return asyncio.run(async_main(argv))
    except EnduranceRunnerError as exc:
        sys.stderr.write(f"Endurance run failed: {exc}\n")
        return 2
    except KeyboardInterrupt:
        sys.stderr.write("Endurance run interrupted.\n")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
