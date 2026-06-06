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
from pathlib import Path
import struct
import sys
import time
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


class EnduranceRunnerError(RuntimeError):
    """Raised for invalid runner configuration or failed validation."""


@dataclass(frozen=True)
class Thresholds:
    max_dropped_chunks: int | None
    max_reconnects: int | None
    max_latency_ms: int | None
    min_received_ratio: float | None


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
            stop_event.set()
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


async def run_endurance(config: RunnerConfig) -> dict[str, object]:
    state = RunnerState()
    source = create_audio_source(config)
    url = build_session_url(config.ws_url, config.session_id)
    started_at = time.time()
    stop_event = asyncio.Event()

    try:
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
            try:
                await asyncio.wait_for(receiver_task, timeout=config.receive_timeout_seconds)
            except TimeoutError:
                stop_event.set()
                receiver_task.cancel()
                await asyncio.gather(receiver_task, return_exceptions=True)
    finally:
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
        "latest_diagnostics": diagnostics,
        "summary": {
            "backend_audio_chunks_received": int_value(diagnostics.get("audio_chunks_received")),
            "backend_audio_chunks_dropped": int_value(diagnostics.get("audio_chunks_dropped")),
            "backend_audio_bytes_received": int_value(diagnostics.get("audio_bytes_received")),
            "backend_received_ratio": received_ratio(
                sent_audio_chunks=state.sent_audio_chunks,
                backend_audio_chunks_received=int_value(diagnostics.get("audio_chunks_received")),
            ),
            "asr_segments": int_value(diagnostics.get("asr_segments")),
            "translation_segments": int_value(diagnostics.get("translation_segments")),
            "revision_segments": int_value(diagnostics.get("revision_segments")),
            "reconnect_count": int_value(diagnostics.get("reconnect_count")),
            "latency": diagnostics.get("latency", {}),
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


def validate_thresholds(report: dict[str, object], thresholds: Thresholds) -> None:
    summary = report.get("summary")
    if not isinstance(summary, dict):
        return

    failures: list[str] = []
    dropped_chunks = int_value(summary.get("backend_audio_chunks_dropped"))
    reconnect_count = int_value(summary.get("reconnect_count"))
    backend_received_ratio = float_value(summary.get("backend_received_ratio"))

    if thresholds.max_dropped_chunks is not None and dropped_chunks > thresholds.max_dropped_chunks:
        failures.append(
            f"dropped chunks {dropped_chunks} > {thresholds.max_dropped_chunks}",
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

    if failures:
        raise EnduranceRunnerError("; ".join(failures))


def write_report(path: Path, report: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


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
    parser.add_argument("--max-reconnects", type=int, default=None)
    parser.add_argument("--max-latency-ms", type=int, default=None)
    parser.add_argument(
        "--min-received-ratio",
        type=float,
        default=None,
        help="Fail if backend received / client sent audio chunk ratio is below this value.",
    )

    args = parser.parse_args(argv)
    if args.duration_seconds <= 0:
        raise EnduranceRunnerError("Duration must be positive.")
    if args.manual_revision_interval_seconds < 0:
        raise EnduranceRunnerError("Manual revision interval cannot be negative.")
    if args.min_received_ratio is not None and not 0 <= args.min_received_ratio <= 1:
        raise EnduranceRunnerError("Minimum received ratio must be between 0 and 1.")

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
            max_reconnects=args.max_reconnects,
            max_latency_ms=args.max_latency_ms,
            min_received_ratio=args.min_received_ratio,
        ),
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
