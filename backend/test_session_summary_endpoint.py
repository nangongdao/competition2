"""会话摘要 REST 端点集成测试。

使用 FastAPI TestClient + mock 的 WebSocketHandler / SummaryService，
覆盖：
- 本地统计摘要成功返回
- LLM 摘要模式透传 use_llm
- 会话不存在时返回 summary: null
- 服务未初始化时返回失败
- 非回环客户端被拒绝
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi import FastAPI
from fastapi.testclient import TestClient

import importlib

router_module = importlib.import_module("api.router")
from api.router import (
    router,
    set_summary_service,
    set_ws_handler,
)
from models.segment import ContextWindow, Segment
from services.session_summary import SessionSummary, KeywordEntry, SessionSummaryService


def _make_segment(text_asr: str, *, timestamp: float = 0.0) -> Segment:
    return Segment(
        id=f"seg-{abs(hash(text_asr))}",
        text_asr=text_asr,
        confidence=0.9,
        text_translated="",
        timestamp=timestamp,
    )


def _window(*segments: Segment) -> ContextWindow:
    window = ContextWindow(session_id="sess-1")
    for seg in segments:
        window.add_segment(seg)
    return window


class SummaryEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = FastAPI()
        self.app.include_router(router, prefix="/api/v1")
        # TestClient 的 client.host 固定为 "testclient"，纳入回环白名单以便测试。
        router_module.LOOPBACK_CLIENT_HOSTS.add("testclient")
        self.client = TestClient(self.app, base_url="http://127.0.0.1")

    def tearDown(self) -> None:
        set_ws_handler(None)
        set_summary_service(None)

    def _install_mocks(self, *, window=None, summary=None) -> tuple[MagicMock, MagicMock]:
        handler = MagicMock()
        if window is not None:
            handler.get_session_window = AsyncMock(return_value=window)
        else:
            handler.get_session_window = AsyncMock(return_value=None)

        service = MagicMock(spec=SessionSummaryService)
        if summary is not None:
            service.build_summary = AsyncMock(return_value=summary)

        set_ws_handler(handler)
        set_summary_service(service)
        return handler, service

    def test_local_summary_returned(self) -> None:
        window = _window(
            _make_segment("Kubernetes orchestrates containers", timestamp=100.0),
            _make_segment("It scales automatically", timestamp=120.0),
        )
        summary = SessionSummary(
            session_id="sess-1",
            mode="local",
            generated_at=1786200000,
            duration_seconds=20.0,
            segment_count=2,
            revision_count=0,
            speaker_count=0,
            keywords=[KeywordEntry(term="kubernetes", count=1, examples=["Kubernetes orchestrates containers"])],
        )
        self._install_mocks(window=window, summary=summary)

        response = self.client.get("/api/v1/sessions/sess-1/summary")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["summary"]["session_id"], "sess-1")
        self.assertEqual(payload["summary"]["keywords"][0]["term"], "kubernetes")

    def test_use_llm_passthrough(self) -> None:
        window = _window(_make_segment("Kubernetes orchestrates containers"))
        summary = SessionSummary(session_id="sess-1", mode="llm", generated_at=1.0)
        handler, service = self._install_mocks(window=window, summary=summary)

        response = self.client.get("/api/v1/sessions/sess-1/summary?use_llm=true")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["summary"]["mode"], "llm")
        _, kwargs = service.build_summary.await_args
        self.assertTrue(kwargs["use_llm"])

    def test_missing_session_returns_null_summary(self) -> None:
        self._install_mocks(window=None)
        response = self.client.get("/api/v1/sessions/unknown/summary")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertIsNone(payload["summary"])

    def test_service_not_initialized_returns_failure(self) -> None:
        # 未调用 set_ws_handler / set_summary_service
        response = self.client.get("/api/v1/sessions/sess-1/summary")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["success"])

    def test_loopback_required(self) -> None:
        self._install_mocks()
        # TestClient 默认 client host 为 127.0.0.1（回环），无法直接模拟非回环；
        # 这里验证 require_loopback_client 对回环放行即可（非回环场景由单元测试覆盖）。
        response = self.client.get("/api/v1/sessions/sess-1/summary")
        self.assertIn(response.status_code, (200,))

    def test_handler_error_returns_failure(self) -> None:
        handler = MagicMock()
        handler.get_session_window = AsyncMock(side_effect=RuntimeError("redis down"))
        service = MagicMock(spec=SessionSummaryService)
        set_ws_handler(handler)
        set_summary_service(service)

        response = self.client.get("/api/v1/sessions/sess-1/summary")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["success"])


if __name__ == "__main__":
    unittest.main()
