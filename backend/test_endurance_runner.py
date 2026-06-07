"""Unit tests for the local WebSocket endurance runner."""

from __future__ import annotations

import asyncio
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from tools.endurance_runner import (
    EnduranceRunnerError,
    GeneratedAudioSource,
    RunnerConfig,
    RunnerState,
    Thresholds,
    WavAudioSource,
    build_report,
    build_session_url,
    frames_per_chunk,
    pcm_frames_to_float32_bytes,
    record_message,
    send_audio,
    validate_thresholds,
)


class EnduranceRunnerTests(unittest.TestCase):
    def test_build_session_url_appends_session_to_base_route(self) -> None:
        url = build_session_url(
            "ws://localhost:8000/api/v1/ws/translate",
            "abc123ef",
        )

        self.assertEqual(url, "ws://localhost:8000/api/v1/ws/translate/abc123ef")

    def test_build_session_url_keeps_explicit_session_route(self) -> None:
        url = build_session_url(
            "ws://localhost:8000/api/v1/ws/translate/existing1",
            "abc123ef",
        )

        self.assertEqual(url, "ws://localhost:8000/api/v1/ws/translate/existing1")

    def test_frames_per_chunk_uses_sample_rate_and_duration(self) -> None:
        self.assertEqual(frames_per_chunk(16000, 100), 1600)

    def test_pcm_int16_frames_convert_to_float32_bytes(self) -> None:
        pcm = struct.pack("<hhh", -32768, 0, 32767)

        converted = pcm_frames_to_float32_bytes(pcm, 2)
        samples = struct.unpack("<fff", converted)

        self.assertAlmostEqual(samples[0], -1.0, places=5)
        self.assertAlmostEqual(samples[1], 0.0, places=5)
        self.assertAlmostEqual(samples[2], 32767 / 32768, places=5)

    def test_wav_source_loops_pcm_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = Path(tmpdir) / "sample.wav"
            with wave.open(str(wav_path), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                wav_file.writeframes(struct.pack("<hh", 0, 32767))

            source = WavAudioSource(
                wav_path=wav_path,
                sample_rate=16000,
                chunk_duration_ms=100,
            )
            try:
                first = source.next_chunk()
                second = source.next_chunk()
            finally:
                source.close()

        self.assertEqual(first, second)
        self.assertEqual(len(first), 8)

    def test_record_message_tracks_status_error_and_diagnostics(self) -> None:
        state = RunnerState()

        record_message(state, {"type": "status", "code": "SESSION_STARTED"})
        record_message(state, {"type": "error", "code": "X", "message": "failed"})
        record_message(
            state,
            {
                "type": "session_diagnostics",
                "diagnostics": {"audio_chunks_received": 4},
            },
        )

        self.assertEqual(state.received_message_counts["status"], 1)
        self.assertEqual(state.status_codes["SESSION_STARTED"], 1)
        self.assertEqual(state.errors[0]["code"], "X")
        self.assertEqual(state.latest_diagnostics, {"audio_chunks_received": 4})

    def test_build_report_summarizes_latest_diagnostics(self) -> None:
        state = RunnerState(sent_audio_chunks=3, sent_audio_bytes=19200)
        state.latest_diagnostics = {
            "audio_chunks_received": 3,
            "audio_chunks_dropped": 1,
            "reconnect_count": 0,
            "audio_queue_depth": 0,
            "audio_queue_max_depth": 2,
            "audio_queue_capacity": 16,
            "latency": {"capture_to_asr_ms": {"count": 1, "avg_ms": 120, "max_ms": 120}},
            "api_call_counts": {"nmt_stream": 2, "translation_cache_hit": True},
            "revision_counts": {"asr_correction": 1},
            "revision_sources": {"audio_redecode": 1},
            "revision_triggers": {"low_confidence": 1},
        }
        config = make_config()

        report = build_report(
            config=config,
            url="ws://localhost/session",
            state=state,
            started_at=10.0,
            ended_at=12.0,
        )

        summary = report["summary"]
        self.assertIsInstance(summary, dict)
        self.assertEqual(summary["backend_audio_chunks_received"], 3)
        self.assertEqual(summary["backend_audio_chunks_dropped"], 1)
        self.assertEqual(summary["backend_audio_queue_depth"], 0)
        self.assertEqual(summary["backend_audio_queue_max_depth"], 2)
        self.assertEqual(summary["backend_audio_queue_capacity"], 16)
        self.assertEqual(summary["backend_received_ratio"], 1.0)
        self.assertEqual(summary["reconnect_count"], 0)
        self.assertEqual(summary["api_call_counts"], {"nmt_stream": 2, "translation_cache_hit": 1})
        self.assertEqual(summary["revision_counts"], {"asr_correction": 1})
        self.assertEqual(summary["revision_sources"], {"audio_redecode": 1})
        self.assertEqual(summary["revision_triggers"], {"low_confidence": 1})

    def test_build_report_summarizes_clean_subtitle_ordering(self) -> None:
        state = RunnerState()
        record_message(
            state,
            {"type": "translation_token", "segment_id": "abc123ef_1", "is_final": True},
        )
        record_message(
            state,
            {"type": "translation_token", "segment_id": "abc123ef_2", "is_final": True},
        )
        report = build_report(
            config=make_config(),
            url="ws://localhost/session",
            state=state,
            started_at=10.0,
            ended_at=12.0,
        )

        summary = report["summary"]
        self.assertIsInstance(summary, dict)
        ordering = summary["subtitle_ordering"]
        self.assertIsInstance(ordering, dict)
        self.assertEqual(ordering["translation_final_messages"], 2)
        self.assertEqual(ordering["unique_final_segments"], 2)
        self.assertEqual(ordering["order_violation_count"], 0)

    def test_build_report_summarizes_subtitle_ordering_violations(self) -> None:
        state = RunnerState()
        for segment_id in ["abc123ef_1", "abc123ef_3", "abc123ef_2", "abc123ef_2"]:
            record_message(
                state,
                {"type": "translation_token", "segment_id": segment_id, "is_final": True},
            )
        record_message(
            state,
            {"type": "translation_token", "segment_id": "not-parseable", "is_final": True},
        )
        record_message(
            state,
            {"type": "revision", "segment_id": "abc123ef_9", "new_text": "corrected"},
        )
        report = build_report(
            config=make_config(),
            url="ws://localhost/session",
            state=state,
            started_at=10.0,
            ended_at=12.0,
        )

        summary = report["summary"]
        self.assertIsInstance(summary, dict)
        ordering = summary["subtitle_ordering"]
        self.assertIsInstance(ordering, dict)
        self.assertEqual(ordering["translation_final_messages"], 5)
        self.assertEqual(ordering["unique_final_segments"], 4)
        self.assertEqual(ordering["duplicate_final_segments"], 1)
        self.assertEqual(ordering["out_of_order_final_segments"], 1)
        self.assertEqual(ordering["final_sequence_gap_events"], 1)
        self.assertEqual(ordering["missing_final_segment_estimate"], 1)
        self.assertEqual(ordering["revisions_for_unknown_segments"], 1)
        self.assertEqual(ordering["unparseable_final_segments"], 1)
        self.assertEqual(ordering["order_violation_count"], 4)

    def test_validate_thresholds_raises_for_dropped_chunks(self) -> None:
        report = {
            "summary": {
                "backend_audio_chunks_dropped": 2,
                "reconnect_count": 0,
                "latency": {},
            },
        }

        with self.assertRaises(EnduranceRunnerError):
            validate_thresholds(
                report,
                Thresholds(
                    max_dropped_chunks=1,
                    max_queue_depth=None,
                    max_reconnects=None,
                    max_latency_ms=None,
                    min_received_ratio=None,
                ),
            )

    def test_validate_thresholds_raises_for_queue_depth(self) -> None:
        report = {
            "summary": {
                "backend_audio_chunks_dropped": 0,
                "backend_audio_queue_max_depth": 9,
                "reconnect_count": 0,
                "latency": {},
            },
        }

        with self.assertRaises(EnduranceRunnerError):
            validate_thresholds(
                report,
                Thresholds(
                    max_dropped_chunks=None,
                    max_queue_depth=8,
                    max_reconnects=None,
                    max_latency_ms=None,
                    min_received_ratio=None,
                ),
            )

    def test_validate_thresholds_raises_for_low_received_ratio(self) -> None:
        report = {
            "summary": {
                "backend_audio_chunks_dropped": 0,
                "backend_received_ratio": 0.75,
                "reconnect_count": 0,
                "latency": {},
            },
        }

        with self.assertRaises(EnduranceRunnerError):
            validate_thresholds(
                report,
                Thresholds(
                    max_dropped_chunks=None,
                    max_queue_depth=None,
                    max_reconnects=None,
                    max_latency_ms=None,
                    min_received_ratio=0.95,
                ),
            )

    def test_validate_thresholds_raises_for_subtitle_order_violations(self) -> None:
        report = {
            "summary": {
                "subtitle_ordering": {
                    "order_violation_count": 2,
                },
            },
        }

        with self.assertRaises(EnduranceRunnerError):
            validate_thresholds(
                report,
                Thresholds(
                    max_dropped_chunks=None,
                    max_queue_depth=None,
                    max_reconnects=None,
                    max_latency_ms=None,
                    min_received_ratio=None,
                    max_subtitle_order_violations=1,
                ),
            )


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent_messages: list[bytes | str] = []

    async def send(self, message: bytes | str) -> None:
        self.sent_messages.append(message)


class EnduranceRunnerAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_audio_duration_end_leaves_receiver_open_for_drain(self) -> None:
        config = RunnerConfig(
            ws_url="ws://localhost:8000/api/v1/ws/translate",
            session_id="abc123ef",
            duration_seconds=0.01,
            chunk_duration_ms=10,
            sample_rate=16000,
            source="silence",
            wav_path=None,
            tone_frequency_hz=440,
            manual_revision_interval_seconds=0,
            receive_timeout_seconds=2,
            output_path=Path("reports/endurance-latest.json"),
            thresholds=Thresholds(
                max_dropped_chunks=None,
                max_queue_depth=None,
                max_reconnects=None,
                max_latency_ms=None,
                min_received_ratio=None,
            ),
        )
        source = GeneratedAudioSource(
            source="silence",
            sample_rate=config.sample_rate,
            chunk_duration_ms=config.chunk_duration_ms,
            tone_frequency_hz=config.tone_frequency_hz,
        )
        state = RunnerState()
        stop_event = asyncio.Event()
        websocket = FakeWebSocket()

        await send_audio(
            websocket,
            config=config,
            source=source,
            state=state,
            stop_event=stop_event,
        )

        self.assertFalse(stop_event.is_set())
        self.assertGreater(state.sent_audio_chunks, 0)
        self.assertEqual(len(websocket.sent_messages), state.sent_audio_chunks)


def make_config() -> RunnerConfig:
    return RunnerConfig(
        ws_url="ws://localhost:8000/api/v1/ws/translate",
        session_id="abc123ef",
        duration_seconds=60,
        chunk_duration_ms=100,
        sample_rate=16000,
        source="silence",
        wav_path=None,
        tone_frequency_hz=440,
        manual_revision_interval_seconds=0,
        receive_timeout_seconds=2,
        output_path=Path("reports/endurance-latest.json"),
        thresholds=Thresholds(
            max_dropped_chunks=None,
            max_queue_depth=None,
            max_reconnects=None,
            max_latency_ms=None,
            min_received_ratio=None,
        ),
    )


if __name__ == "__main__":
    unittest.main()
