"""Tests for session data lifecycle & privacy control (ROADMAP Phase 10)."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from services.session_data_service import SessionDataService


class SessionDataServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.storage_path = Path(self._tmp.name) / "session-history.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def make_service(self, *, retention_seconds: int | None = None) -> SessionDataService:
        return SessionDataService(
            storage_path=self.storage_path,
            retention_seconds=retention_seconds,
        )

    def test_record_start_creates_entry(self) -> None:
        service = self.make_service()
        service.record_session_start("session-a")

        sessions = service.list_sessions()
        self.assertEqual(len(sessions), 1)
        record = sessions[0]
        self.assertEqual(record["session_id"], "session-a")
        self.assertEqual(record["segment_count"], 0)
        self.assertIn("started_at", record)

    def test_update_progress_accumulates(self) -> None:
        service = self.make_service()
        service.record_session_start("session-a")
        service.update_session_progress("session-a", segment_count=12, duration_ms=34000)

        record = service.list_sessions()[0]
        self.assertEqual(record["segment_count"], 12)
        self.assertEqual(record["duration_ms"], 34000)

    def test_update_progress_ignores_unknown_session(self) -> None:
        service = self.make_service()
        service.update_session_progress("ghost", segment_count=5)
        self.assertEqual(len(service.list_sessions()), 0)

    def test_record_start_includes_empty_quality(self) -> None:
        service = self.make_service()
        service.record_session_start("session-a")
        record = service.list_sessions()[0]
        self.assertIn("quality", record)
        self.assertEqual(record["quality"]["asr_segments"], 0)
        self.assertEqual(record["quality"]["translation_segments"], 0)

    def test_update_quality_persists_metrics(self) -> None:
        service = self.make_service()
        service.record_session_start("session-a")
        service.update_session_quality("session-a", {
            "asr_segments": 10,
            "translation_segments": 9,
            "revision_segments": 2,
            "audio_chunks_received": 500,
            "audio_chunks_dropped": 1,
            "audio_queue_max_depth": 14,
            "audio_queue_capacity": 100,
            "reconnect_count": 0,
            "latency": {
                "asr_to_translation_final_ms": {"count": 9, "avg_ms": 1900, "max_ms": 2500},
            },
            "api_call_counts": {"nmt": 9},
        })
        record = service.list_sessions()[0]
        quality = record["quality"]
        self.assertEqual(quality["asr_segments"], 10)
        self.assertEqual(quality["audio_chunks_dropped"], 1)
        self.assertEqual(quality["audio_queue_max_depth"], 14)
        self.assertEqual(
            quality["latency"]["asr_to_translation_final_ms"]["avg_ms"],
            1900,
        )

    def test_update_quality_ignores_unknown_session(self) -> None:
        service = self.make_service()
        service.update_session_quality("ghost", {"asr_segments": 1})
        self.assertEqual(len(service.list_sessions()), 0)

    def test_update_quality_merges_with_empty_template(self) -> None:
        service = self.make_service()
        service.record_session_start("session-a")
        service.update_session_quality("session-a", {"revision_segments": 3})
        record = service.list_sessions()[0]
        quality = record["quality"]
        self.assertEqual(quality["revision_segments"], 3)
        # 未提供的字段保留空模板默认值
        self.assertEqual(quality["asr_segments"], 0)
        self.assertEqual(quality["translation_segments"], 0)

    def test_quality_survives_reload(self) -> None:
        service = self.make_service()
        service.record_session_start("session-a")
        service.update_session_quality("session-a", {"asr_segments": 7})

        reloaded = self.make_service()
        record = reloaded.list_sessions()[0]
        self.assertEqual(record["quality"]["asr_segments"], 7)

    def test_delete_session_removes_entry(self) -> None:
        service = self.make_service()
        service.record_session_start("session-a")
        service.record_session_start("session-b")

        self.assertTrue(service.delete_session("session-a"))
        remaining = service.list_sessions()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["session_id"], "session-b")

        # 删除不存在的会话返回 False
        self.assertFalse(service.delete_session("session-a"))

    def test_clear_all_empties_ledger(self) -> None:
        service = self.make_service()
        service.record_session_start("session-a")
        service.record_session_start("session-b")

        cleared = service.clear_all()
        self.assertEqual(cleared, 2)
        self.assertEqual(len(service.list_sessions()), 0)

    def test_purge_expired_removes_old_only(self) -> None:
        service = self.make_service(retention_seconds=100)
        service.record_session_start("old-session")
        service.record_session_start("new-session")

        # 把 old-session 的开始时间拨回 200 秒前（超过保留期）
        with service._lock:
            service._sessions["old-session"]["started_at"] = time.time() - 200
            service._sessions["new-session"]["started_at"] = time.time()

        purged = service.purge_expired()
        self.assertEqual(purged, 1)
        remaining = service.list_sessions()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["session_id"], "new-session")

    def test_stats_totals(self) -> None:
        service = self.make_service()
        service.record_session_start("session-a")
        service.record_session_start("session-b")
        service.update_session_progress("session-a", segment_count=10)

        stats = service.stats()
        self.assertEqual(stats["total_sessions"], 2)
        self.assertEqual(stats["total_segments"], 10)
        self.assertGreater(stats["retention_seconds"], 0)

    def test_persistence_survives_reload(self) -> None:
        service = self.make_service()
        service.record_session_start("session-a")
        service.update_session_progress("session-a", segment_count=7)

        # 重新加载（同一路径）：台账应从磁盘恢复
        reloaded = self.make_service()
        sessions = reloaded.list_sessions()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["segment_count"], 7)

    def test_corrupted_storage_degrades_gracefully(self) -> None:
        self.storage_path.write_text("{not valid json", encoding="utf-8")
        service = self.make_service()
        self.assertEqual(service.size, 0)
        # 损坏后仍可正常写入
        service.record_session_start("session-a")
        self.assertEqual(service.size, 1)


if __name__ == "__main__":
    unittest.main()
