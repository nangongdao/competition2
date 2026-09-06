"""协作翻译与订阅 REST 端点集成测试（ROADMAP V5.2 / V5.5）。

使用 FastAPI TestClient + mock 覆盖：
- 协作房间 list / create / get / join / leave / revisions / destroy
- 订阅 get / put / reset
- 服务未初始化时返回失败
- 回环客户端校验
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi import FastAPI
from fastapi.testclient import TestClient

import importlib

router_module = importlib.import_module("api.router")
from api.router import (
    router,
    set_ws_handler,
)
from services.collaboration import CollaborationService, set_collaboration_service
from services.subscription import SubscriptionService, set_subscription_service


class CollaborationEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = FastAPI()
        self.app.include_router(router, prefix="/api/v1")
        router_module.LOOPBACK_CLIENT_HOSTS.add("testclient")
        self.client = TestClient(self.app, base_url="http://127.0.0.1")

        self.service = CollaborationService()
        set_collaboration_service(self.service)

    def tearDown(self) -> None:
        set_collaboration_service(None)
        set_ws_handler(None)

    def test_list_rooms_empty(self) -> None:
        response = self.client.get("/api/v1/collaboration/rooms")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["rooms"], [])

    def test_create_room(self) -> None:
        response = self.client.post("/api/v1/collaboration/rooms", json={
            "ownerSessionId": "session-abc",
            "title": "产品评审",
        })
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["room"]["title"], "产品评审")
        self.assertEqual(payload["room"]["member_count"], 1)

    def test_create_room_missing_owner(self) -> None:
        response = self.client.post("/api/v1/collaboration/rooms", json={
            "ownerSessionId": "",
        })
        payload = response.json()
        self.assertFalse(payload["success"])

    def test_join_room(self) -> None:
        created = self.client.post("/api/v1/collaboration/rooms", json={
            "ownerSessionId": "owner",
            "title": "会议",
        }).json()["room"]
        response = self.client.post(
            f"/api/v1/collaboration/rooms/{created['room_id']}/join",
            json={"sessionId": "member-1", "name": "小明"},
        )
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["room"]["member_count"], 2)

    def test_submit_revision(self) -> None:
        created = self.client.post("/api/v1/collaboration/rooms", json={
            "ownerSessionId": "owner",
            "title": "会议",
        }).json()["room"]
        response = self.client.post(
            f"/api/v1/collaboration/rooms/{created['room_id']}/revisions",
            json={
                "sessionId": "owner",
                "segmentId": "seg_1",
                "newText": "修正译文",
                "sourceText": "source",
            },
        )
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["revision"]["new_text"], "修正译文")

    def test_leave_owner_destroys_room(self) -> None:
        created = self.client.post("/api/v1/collaboration/rooms", json={
            "ownerSessionId": "owner",
            "title": "会议",
        }).json()["room"]
        response = self.client.post(
            f"/api/v1/collaboration/rooms/{created['room_id']}/leave",
            json={"sessionId": "owner"},
        )
        self.assertTrue(response.json()["success"])
        # 房间已销毁
        response = self.client.get(f"/api/v1/collaboration/rooms/{created['room_id']}")
        self.assertFalse(response.json()["success"])

    def test_service_not_initialized(self) -> None:
        set_collaboration_service(None)
        response = self.client.get("/api/v1/collaboration/rooms")
        payload = response.json()
        self.assertFalse(payload["success"])


class SubscriptionEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = FastAPI()
        self.app.include_router(router, prefix="/api/v1")
        router_module.LOOPBACK_CLIENT_HOSTS.add("testclient")
        self.client = TestClient(self.app, base_url="http://127.0.0.1")

        self._tmpdir = tempfile.TemporaryDirectory()
        self.service = SubscriptionService(
            path=Path(self._tmpdir.name) / "subscription.test.json",
        )
        set_subscription_service(self.service)

    def tearDown(self) -> None:
        set_subscription_service(None)
        set_ws_handler(None)
        self._tmpdir.cleanup()

    def test_get_subscription_free_default(self) -> None:
        response = self.client.get("/api/v1/subscription")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["subscription"]["plan"], "free")
        self.assertEqual(len(payload["plans"]), 4)

    def test_update_subscription(self) -> None:
        response = self.client.put("/api/v1/subscription", json={"plan": "team"})
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["subscription"]["plan"], "team")

    def test_update_subscription_invalid(self) -> None:
        response = self.client.put("/api/v1/subscription", json={"plan": "gold"})
        payload = response.json()
        self.assertFalse(payload["success"])

    def test_reset_usage(self) -> None:
        self.service.consume()
        response = self.client.post("/api/v1/subscription/reset")
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["subscription"]["daily_used"], 0)

    def test_service_not_initialized(self) -> None:
        set_subscription_service(None)
        response = self.client.get("/api/v1/subscription")
        payload = response.json()
        self.assertFalse(payload["success"])


if __name__ == "__main__":
    unittest.main()
