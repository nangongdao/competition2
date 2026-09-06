"""会话数据生命周期 REST 端点集成测试（ROADMAP Phase 10）。

使用 FastAPI TestClient + mock 覆盖：
- GET /api/v1/session-history 列表与统计
- DELETE /api/v1/session-history/{id} 删除单条
- DELETE /api/v1/session-history 清空全部
- POST /api/v1/session-history/purge 过期清理
- 服务未初始化时返回失败
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient

router_module = importlib.import_module("api.router")
from api.router import router, set_ws_handler
from services.session_data_service import SessionDataService, set_session_data_service


class SessionHistoryEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = FastAPI()
        self.app.include_router(router, prefix="/api/v1")
        router_module.LOOPBACK_CLIENT_HOSTS.add("testclient")
        self.client = TestClient(self.app, base_url="http://127.0.0.1")

        self._tmpdir = tempfile.TemporaryDirectory()
        self.service = SessionDataService(
            storage_path=Path(self._tmpdir.name) / "session-history.test.json",
        )
        set_session_data_service(self.service)

    def tearDown(self) -> None:
        set_session_data_service(None)
        set_ws_handler(None)
        self._tmpdir.cleanup()

    def test_list_empty_history(self) -> None:
        response = self.client.get("/api/v1/session-history")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["sessions"], [])
        self.assertEqual(payload["stats"]["total_sessions"], 0)

    def test_list_after_record(self) -> None:
        self.service.record_session_start("session-a")
        self.service.update_session_progress("session-a", segment_count=5)

        response = self.client.get("/api/v1/session-history")
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(len(payload["sessions"]), 1)
        self.assertEqual(payload["sessions"][0]["session_id"], "session-a")
        self.assertEqual(payload["sessions"][0]["segment_count"], 5)
        self.assertEqual(payload["stats"]["total_sessions"], 1)

    def test_delete_single_session(self) -> None:
        self.service.record_session_start("session-a")
        self.service.record_session_start("session-b")

        response = self.client.delete("/api/v1/session-history/session-a")
        self.assertTrue(response.json()["success"])

        sessions = self.client.get("/api/v1/session-history").json()["sessions"]
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["session_id"], "session-b")

    def test_delete_missing_session_returns_failure(self) -> None:
        response = self.client.delete("/api/v1/session-history/ghost")
        payload = response.json()
        self.assertFalse(payload["success"])

    def test_clear_all(self) -> None:
        self.service.record_session_start("session-a")
        self.service.record_session_start("session-b")

        response = self.client.delete("/api/v1/session-history")
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["cleared"], 2)
        self.assertEqual(
            self.client.get("/api/v1/session-history").json()["stats"]["total_sessions"],
            0,
        )

    def test_purge_endpoint(self) -> None:
        # 用极短保留期让旧会话过期
        self.service._retention_seconds = -1
        self.service.record_session_start("old-session")
        self.service.record_session_start("new-session")

        response = self.client.post("/api/v1/session-history/purge")
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertGreaterEqual(payload["purged"], 1)

    def test_service_not_initialized(self) -> None:
        set_session_data_service(None)
        response = self.client.get("/api/v1/session-history")
        payload = response.json()
        self.assertFalse(payload["success"])
        self.assertIn("not initialized", payload["reason"])


if __name__ == "__main__":
    unittest.main()
