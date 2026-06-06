import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.session_diagnostics import SessionDiagnostics


class SessionDiagnosticsTests(unittest.TestCase):
    def test_snapshot_contains_latency_and_counter_summaries(self) -> None:
        diagnostics = SessionDiagnostics(session_id="s1")

        diagnostics.record_audio_chunk(3200)
        diagnostics.record_audio_chunk(1600)
        diagnostics.record_dropped_audio_chunk()
        diagnostics.record_asr_segment(2100)
        diagnostics.record_translation_segment(
            first_token_latency_ms=250,
            final_latency_ms=900,
        )
        diagnostics.record_revision(
            reason="asr_correction",
            source="audio_redecode",
            trigger="low_confidence",
            latency_ms=640,
        )
        diagnostics.record_api_call("nmt_complete", 2)
        diagnostics.set_reconnect_count(1)

        snapshot = diagnostics.snapshot()

        self.assertEqual(snapshot["session_id"], "s1")
        self.assertEqual(snapshot["audio_chunks_received"], 2)
        self.assertEqual(snapshot["audio_bytes_received"], 4800)
        self.assertEqual(snapshot["audio_chunks_dropped"], 1)
        self.assertEqual(snapshot["asr_segments"], 1)
        self.assertEqual(snapshot["translation_segments"], 1)
        self.assertEqual(snapshot["revision_segments"], 1)
        self.assertEqual(snapshot["reconnect_count"], 1)
        self.assertEqual(snapshot["api_call_counts"]["nmt_stream"], 1)
        self.assertEqual(snapshot["api_call_counts"]["nmt_complete"], 2)
        self.assertEqual(snapshot["revision_counts"]["asr_correction"], 1)
        self.assertEqual(snapshot["revision_sources"]["audio_redecode"], 1)
        self.assertEqual(snapshot["revision_triggers"]["low_confidence"], 1)
        self.assertEqual(snapshot["latency"]["capture_to_asr_ms"]["avg_ms"], 2100)
        self.assertEqual(snapshot["latency"]["asr_to_first_token_ms"]["max_ms"], 250)
        self.assertEqual(snapshot["latency"]["asr_to_translation_final_ms"]["count"], 1)
        self.assertEqual(snapshot["latency"]["revision_final_ms"]["avg_ms"], 640)


if __name__ == "__main__":
    unittest.main()
