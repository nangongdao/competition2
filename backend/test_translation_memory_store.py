"""Unit tests for the cross-session translation memory store (V5.3 production)."""

from __future__ import annotations

import tempfile
from pathlib import Path
import sys
import unittest


BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.translation_memory import TranslationMemoryService
from services.translation_memory_store import (
    TranslationMemoryStore,
    get_tm_store,
    set_tm_store,
)


class TranslationMemoryStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self._tmpdir.name) / "tm-store.json"
        self.store = TranslationMemoryStore(path=self.path)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _reload(self) -> TranslationMemoryStore:
        """重新加载（模拟进程重启后从磁盘恢复）。"""
        return TranslationMemoryStore(path=self.path)

    def test_add_and_size(self) -> None:
        self.assertTrue(
            self.store.add("Hello world", "你好，世界", language_pair="en->zh-CN")
        )
        self.assertEqual(self.store.size(), 1)
        self.assertEqual(self.store.size_by_pair("en->zh-CN"), 1)

    def test_add_rejects_empty(self) -> None:
        self.assertFalse(self.store.add("", "你好"))
        self.assertFalse(self.store.add("Hello", "  "))
        self.assertEqual(self.store.size(), 0)

    def test_lookup_exact_hit(self) -> None:
        self.store.add("Hello world", "你好，世界", language_pair="en->zh-CN")
        hit = self.store.lookup("Hello world", language_pair="en->zh-CN")
        self.assertIsNotNone(hit)
        self.assertEqual(hit["translated"], "你好，世界")

    def test_lookup_respects_language_pair(self) -> None:
        self.store.add("Hello world", "你好，世界", language_pair="en->zh-CN")
        self.assertIsNone(self.store.lookup("Hello world", language_pair="zh-CN->en"))
        self.assertIsNotNone(self.store.lookup("Hello world", language_pair="en->zh-CN"))

    def test_lookup_case_and_punctuation_insensitive(self) -> None:
        self.store.add("Hello, World!", "你好，世界", language_pair="en->zh-CN")
        hit = self.store.lookup("hello world", language_pair="en->zh-CN")
        self.assertIsNotNone(hit)

    def test_lookup_miss(self) -> None:
        self.assertIsNone(self.store.lookup("nothing here"))

    def test_persist_and_reload_roundtrip(self) -> None:
        self.store.add("Hello world", "你好，世界", language_pair="en->zh-CN")
        self.store.add("Good morning", "早上好", language_pair="en->zh-CN")
        reloaded = self._reload()
        self.assertEqual(reloaded.size(), 2)
        hit = reloaded.lookup("Hello world", language_pair="en->zh-CN")
        self.assertEqual(hit["translated"], "你好，世界")
        hit2 = reloaded.lookup("good morning", language_pair="en->zh-CN")
        self.assertEqual(hit2["translated"], "早上好")

    def test_duplicate_add_updates_translation(self) -> None:
        self.store.add("Hello world", "你好，世界", language_pair="en->zh-CN")
        self.store.add("Hello world", "你好世界（修订）", language_pair="en->zh-CN")
        self.assertEqual(self.store.size(), 1)
        hit = self.store.lookup("Hello world", language_pair="en->zh-CN")
        self.assertEqual(hit["translated"], "你好世界（修订）")

    def test_reload_after_update_keeps_latest(self) -> None:
        self.store.add("Hello world", "你好，世界", language_pair="en->zh-CN")
        reloaded = self._reload()
        reloaded.add("Hello world", "你好世界（修订）", language_pair="en->zh-CN")
        final = self._reload()
        hit = final.lookup("Hello world", language_pair="en->zh-CN")
        self.assertEqual(hit["translated"], "你好世界（修订）")

    def test_all_entries_sorted_by_created_at_desc(self) -> None:
        self.store.add("First", "一", language_pair="en->zh-CN")
        self.store.add("Second", "二", language_pair="en->zh-CN")
        entries = self.store.all_entries(limit=10)
        self.assertEqual(len(entries), 2)
        # 最近写入的在前
        self.assertEqual(entries[0]["source"], "Second")

    def test_pair_entries_filter(self) -> None:
        self.store.add("Hello", "你好", language_pair="en->zh-CN")
        self.store.add("Bonjour", "你好（法）", language_pair="fr->zh-CN")
        self.assertEqual(len(self.store.pair_entries("en->zh-CN")), 1)
        self.assertEqual(len(self.store.pair_entries("fr->zh-CN")), 1)

    def test_clear_pair(self) -> None:
        self.store.add("Hello", "你好", language_pair="en->zh-CN")
        self.store.add("Bonjour", "你好（法）", language_pair="fr->zh-CN")
        self.assertEqual(self.store.clear_pair("en->zh-CN"), 1)
        self.assertEqual(self.store.size(), 1)
        # 持久化后依然生效
        reloaded = self._reload()
        self.assertEqual(reloaded.size(), 1)

    def test_clear_all(self) -> None:
        self.store.add("Hello", "你好", language_pair="en->zh-CN")
        self.store.add("Bonjour", "你好（法）", language_pair="fr->zh-CN")
        self.assertEqual(self.store.clear_all(), 2)
        self.assertEqual(self.store.size(), 0)
        reloaded = self._reload()
        self.assertEqual(reloaded.size(), 0)

    def test_corrupt_file_safe_degrade(self) -> None:
        self.path.write_text("{not valid json", encoding="utf-8")
        store = TranslationMemoryStore(path=self.path)
        self.assertEqual(store.size(), 0)

    def test_capacity_bounded(self) -> None:
        store = TranslationMemoryStore(
            path=self.path,
            max_entries=50,
        )
        for index in range(70):
            store.add(f"sentence {index}", f"译文 {index}", language_pair="en->zh-CN")
        self.assertLessEqual(store.size(), 50)

    def test_stats(self) -> None:
        self.store.add("Hello", "你好", language_pair="en->zh-CN")
        self.store.add("Bonjour", "你好（法）", language_pair="fr->zh-CN")
        stats = self.store.stats()
        self.assertEqual(stats["size"], 2)
        self.assertEqual(stats["pairs"], 2)
        self.assertIn("by_pair", stats)


class TranslationMemoryServicePersistenceTests(unittest.TestCase):
    """会话级 TM 与持久化存储联动测试。"""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self._tmpdir.name) / "tm-store.json"
        self.store = TranslationMemoryStore(path=self.path)
        self.tm = TranslationMemoryService(
            session_id="test-session",
            store=self.store,
        )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_add_writes_to_store(self) -> None:
        self.tm.add("Hello world", "你好，世界", language_pair="en->zh-CN")
        self.assertEqual(self.store.size(), 1)

    def test_lookup_falls_back_to_store(self) -> None:
        # 持久化层已有历史记忆（模拟上一场会话写入）
        self.store.add("Hello world", "你好，世界", language_pair="en->zh-CN")
        match = self.tm.lookup("Hello world", language_pair="en->zh-CN")
        self.assertIsNotNone(match)
        self.assertEqual(match.translated, "你好，世界")
        self.assertEqual(match.similarity, 1.0)

    def test_lookup_prefers_session_memory(self) -> None:
        self.store.add("Hello world", "历史译文", language_pair="en->zh-CN")
        self.tm.add("Hello world", "本次会话译文", language_pair="en->zh-CN")
        match = self.tm.lookup("Hello world", language_pair="en->zh-CN")
        self.assertEqual(match.translated, "本次会话译文")

    def test_lookup_respects_language_pair_in_store(self) -> None:
        self.store.add("Hello world", "你好，世界", language_pair="en->zh-CN")
        self.assertIsNone(self.tm.lookup("Hello world", language_pair="zh-CN->en"))

    def test_cross_session_accumulation_flow(self) -> None:
        """完整跨会话流程：会话 A 写入 -> 会话 B 复用。"""
        session_a = TranslationMemoryService(
            session_id="session-a",
            store=self.store,
        )
        session_a.add("The quick brown fox", "敏捷的棕色狐狸", language_pair="en->zh-CN")

        # 新会话 B（同一持久化存储）
        session_b = TranslationMemoryService(
            session_id="session-b",
            store=self.store,
        )
        match = session_b.lookup("The quick brown fox", language_pair="en->zh-CN")
        self.assertIsNotNone(match)
        self.assertEqual(match.translated, "敏捷的棕色狐狸")


class TmStoreSingletonTests(unittest.TestCase):
    def tearDown(self) -> None:
        set_tm_store(None)

    def test_get_set_singleton(self) -> None:
        self.assertIsNone(get_tm_store())
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TranslationMemoryStore(path=Path(tmpdir) / "tm.json")
            set_tm_store(store)
            self.assertIs(get_tm_store(), store)
        set_tm_store(None)
        self.assertIsNone(get_tm_store())


if __name__ == "__main__":
    unittest.main()
