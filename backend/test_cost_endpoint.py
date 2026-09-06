"""REST 端点集成测试：商用成本模型 /cost 与 /cost/reset。

使用 FastAPI TestClient + mock 覆盖 require_loopback_client 校验，
验证 /cost 概览返回与 /cost/reset 清空逻辑。
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import importlib  # noqa: E402

router_module = importlib.import_module("api.router")
from api.router import (  # noqa: E402
    router,
    set_ws_handler,
)
from services.cost_service import CostService, set_cost_service  # noqa: E402


class CostEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = FastAPI()
        self.app.include_router(router, prefix="/api/v1")
        router_module.LOOPBACK_CLIENT_HOSTS.add("testclient")
        self.client = TestClient(self.app, base_url="http://127.0.0.1")

        temp_dir = tempfile.mkdtemp()
        self.service = CostService(path=Path(temp_dir) / "cost.json")
        set_cost_service(self.service)

    def tearDown(self) -> None:
        set_cost_service(None)
        set_ws_handler(None)

    def test_get_cost_overview_empty(self) -> None:
        response = self.client.get("/api/v1/cost")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["total_sessions"], 0)
        self.assertEqual(payload["usage"]["nmt_input_tokens"], 0)
        self.assertIn("total_cost_usd", payload)
        self.assertIn("suggestions", payload)

    def test_record_then_get(self) -> None:
        self.service.record_nmt("hello world this is a test sentence", "你好世界这是一句测试")
        response = self.client.get("/api/v1/cost")
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertGreater(payload["usage"]["nmt_input_tokens"], 0)
        self.assertGreater(payload["usage"]["nmt_output_tokens"], 0)

    def test_reset_cost_usage(self) -> None:
        self.service.record_asr(60.0)
        response = self.client.post("/api/v1/cost/reset")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["usage"]["asr_seconds"], 0)
        self.assertEqual(payload["total_sessions"], 0)


if __name__ == "__main__":
    unittest.main()
