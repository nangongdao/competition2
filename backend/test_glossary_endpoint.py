"""术语库与翻译记忆库 REST 端点集成测试。

使用 FastAPI TestClient + mock 覆盖：
- 术语库 list / add / delete / clear / import
- 翻译记忆库 stats / clear
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
from services.glossary_manager import GlossaryManager, set_glossary_manager


class GlossaryEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = FastAPI()
        self.app.include_router(router, prefix="/api/v1")
        router_module.LOOPBACK_CLIENT_HOSTS.add("testclient")
        self.client = TestClient(self.app, base_url="http://127.0.0.1")

        self._tmpdir = tempfile.TemporaryDirectory()
        self.manager = GlossaryManager(
            path=Path(self._tmpdir.name) / "glossary.test.json",
        )
        set_glossary_manager(self.manager)

    def tearDown(self) -> None:
        set_glossary_manager(None)
        set_ws_handler(None)
        self._tmpdir.cleanup()

    def test_get_glossary_empty(self) -> None:
        response = self.client.get("/api/v1/glossary")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["glossary"]["size"], 0)
        self.assertEqual(payload["glossary"]["entries"], [])

    def test_add_glossary_entry(self) -> None:
        response = self.client.post("/api/v1/glossary", json={
            "source": "Kubernetes",
            "target": "容器编排平台",
        })
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["entry"]["source"], "Kubernetes")

        # 再次读取应包含该条目
        response = self.client.get("/api/v1/glossary")
        self.assertEqual(response.json()["glossary"]["size"], 1)

    def test_add_duplicate_returns_failure(self) -> None:
        self.client.post("/api/v1/glossary", json={"source": "K8s", "target": "Kubernetes"})
        response = self.client.post("/api/v1/glossary", json={"source": "k8s", "target": "X"})
        payload = response.json()
        self.assertFalse(payload["success"])
        self.assertIn("已存在", payload["reason"])

    def test_delete_glossary_entry(self) -> None:
        entry = self.client.post("/api/v1/glossary", json={
            "source": "LLM",
            "target": "大语言模型",
        }).json()["entry"]

        response = self.client.delete(f"/api/v1/glossary/{entry['id']}")
        self.assertTrue(response.json()["success"])
        self.assertEqual(self.client.get("/api/v1/glossary").json()["glossary"]["size"], 0)

    def test_clear_glossary(self) -> None:
        self.client.post("/api/v1/glossary", json={"source": "A", "target": "甲"})
        self.client.post("/api/v1/glossary", json={"source": "B", "target": "乙"})

        response = self.client.delete("/api/v1/glossary")
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["cleared"], 2)
        self.assertEqual(self.client.get("/api/v1/glossary").json()["glossary"]["size"], 0)

    def test_import_glossary_csv(self) -> None:
        response = self.client.post("/api/v1/glossary/import", json={
            "csv": "ML,机器学习\nLLM,大语言模型,true\n",
        })
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["imported"], 2)
        self.assertEqual(self.client.get("/api/v1/glossary").json()["glossary"]["size"], 2)

    def test_import_glossary_entries(self) -> None:
        response = self.client.post("/api/v1/glossary/import", json={
            "entries": [
                {"source": "Golang", "target": "Go 语言"},
                {"source": "Rust", "target": "锈"},
            ],
        })
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["imported"], 2)

    def test_import_without_payload_returns_failure(self) -> None:
        response = self.client.post("/api/v1/glossary/import", json={})
        self.assertFalse(response.json()["success"])

    def test_service_not_initialized_returns_failure(self) -> None:
        set_glossary_manager(None)
        response = self.client.get("/api/v1/glossary")
        self.assertFalse(response.json()["success"])


class TranslationMemoryEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = FastAPI()
        self.app.include_router(router, prefix="/api/v1")
        router_module.LOOPBACK_CLIENT_HOSTS.add("testclient")
        self.client = TestClient(self.app, base_url="http://127.0.0.1")

    def tearDown(self) -> None:
        set_ws_handler(None)

    def test_stats_returns_empty_when_no_handler(self) -> None:
        response = self.client.get("/api/v1/translation-memory")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["success"])

    def test_stats_aggregates_from_handler(self) -> None:
        from unittest.mock import MagicMock

        handler = MagicMock()
        handler.translation_memory_summary.return_value = {
            "size": 3,
            "hits": 1,
            "misses": 2,
            "written": 3,
            "sessions": ["sess-1"],
            "threshold": 0.82,
        }
        set_ws_handler(handler)

        response = self.client.get("/api/v1/translation-memory")
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["stats"]["size"], 3)
        self.assertEqual(payload["stats"]["hits"], 1)

    def test_clear_calls_handler(self) -> None:
        from unittest.mock import MagicMock

        handler = MagicMock()
        handler.clear_translation_memory.return_value = 2
        set_ws_handler(handler)

        response = self.client.post("/api/v1/translation-memory/clear")
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["cleared"], 2)
        handler.clear_translation_memory.assert_called_once()


class TranslationMemoryStoreEndpointTests(unittest.TestCase):
    """跨会话持久化翻译记忆库 REST 端点测试（V5.3 生产化）。"""

    def setUp(self) -> None:
        self.app = FastAPI()
        self.app.include_router(router, prefix="/api/v1")
        router_module.LOOPBACK_CLIENT_HOSTS.add("testclient")
        self.client = TestClient(self.app, base_url="http://127.0.0.1")

        self._tmpdir = tempfile.TemporaryDirectory()
        from services.translation_memory_store import (
            TranslationMemoryStore,
            set_tm_store as _set_tm_store,
        )

        self._set_tm_store = _set_tm_store
        self.store = TranslationMemoryStore(
            path=Path(self._tmpdir.name) / "tm-store.test.json",
            max_entries=100,
        )
        _set_tm_store(self.store)

    def tearDown(self) -> None:
        self._set_tm_store(None)
        set_ws_handler(None)
        self._tmpdir.cleanup()

    def test_stats_includes_store_when_not_persisted(self) -> None:
        # 未初始化全局 store 时 store 统计标记 persisted=False
        self._set_tm_store(None)
        from unittest.mock import MagicMock

        handler = MagicMock()
        handler.translation_memory_summary.return_value = {
            "size": 0,
            "hits": 0,
            "misses": 0,
            "written": 0,
            "sessions": [],
            "threshold": 0.82,
        }
        set_ws_handler(handler)

        response = self.client.get("/api/v1/translation-memory")
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertIn("store", payload["stats"])
        self.assertFalse(payload["stats"]["store"]["persisted"])

    def test_stats_includes_persisted_store(self) -> None:
        from unittest.mock import MagicMock

        handler = MagicMock()
        handler.translation_memory_summary.return_value = {
            "size": 1,
            "hits": 1,
            "misses": 0,
            "written": 1,
            "sessions": ["sess-1"],
            "threshold": 0.82,
        }
        set_ws_handler(handler)
        self.store.add("Hello world", "你好，世界", language_pair="en->zh-CN")

        response = self.client.get("/api/v1/translation-memory")
        payload = response.json()
        self.assertTrue(payload["success"])
        store_stats = payload["stats"]["store"]
        self.assertTrue(store_stats["persisted"])
        self.assertEqual(store_stats["size"], 1)
        self.assertEqual(store_stats["pairs"], 1)

    def test_entries_endpoint_returns_stored_pairs(self) -> None:
        self.store.add("Hello world", "你好，世界", language_pair="en->zh-CN")
        self.store.add("Good morning", "早上好", language_pair="en->zh-CN")

        response = self.client.get("/api/v1/translation-memory/entries")
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["size"], 2)
        sources = {entry["source"] for entry in payload["entries"]}
        self.assertIn("Hello world", sources)

    def test_entries_endpoint_filters_by_language_pair(self) -> None:
        self.store.add("Hello", "你好", language_pair="en->zh-CN")
        self.store.add("Bonjour", "你好（法）", language_pair="fr->zh-CN")

        response = self.client.get(
            "/api/v1/translation-memory/entries",
            params={"language_pair": "fr->zh-CN"},
        )
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["size"], 1)
        self.assertEqual(payload["entries"][0]["language_pair"], "fr->zh-CN")

    def test_entries_endpoint_when_store_not_initialized(self) -> None:
        self._set_tm_store(None)
        response = self.client.get("/api/v1/translation-memory/entries")
        payload = response.json()
        self.assertFalse(payload["success"])

    def test_clear_clears_persisted_store(self) -> None:
        from unittest.mock import MagicMock

        handler = MagicMock()
        handler.clear_translation_memory.return_value = 0
        set_ws_handler(handler)
        self.store.add("Hello world", "你好，世界", language_pair="en->zh-CN")

        response = self.client.post("/api/v1/translation-memory/clear")
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["store_cleared"], 1)
        self.assertEqual(self.store.size(), 0)


if __name__ == "__main__":
    unittest.main()
