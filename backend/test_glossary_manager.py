"""Unit tests for the glossary manager (V5.1 persistence + management)."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.glossary_manager import (
    GlossaryError,
    GlossaryManager,
)


class GlossaryManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self._tmpdir.name) / "glossary.test.json"
        self.manager = GlossaryManager(path=self.path)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_starts_empty(self) -> None:
        self.assertEqual(self.manager.size, 0)
        self.assertEqual(self.manager.list_entries(), [])

    def test_add_entry(self) -> None:
        entry = self.manager.add_entry("Kubernetes", "容器编排平台")
        self.assertEqual(entry["source"], "Kubernetes")
        self.assertEqual(entry["target"], "容器编排平台")
        self.assertFalse(entry["keep_original"])
        self.assertEqual(self.manager.size, 1)

    def test_add_entry_keep_original(self) -> None:
        entry = self.manager.add_entry("LLM", "", keep_original=True)
        self.assertTrue(entry["keep_original"])
        self.assertEqual(entry["target"], "")

    def test_add_entry_rejects_empty_source(self) -> None:
        with self.assertRaises(GlossaryError):
            self.manager.add_entry("  ", "译")

    def test_add_entry_rejects_duplicate_case_insensitive(self) -> None:
        self.manager.add_entry("Kubernetes", "K8s")
        with self.assertRaises(GlossaryError):
            self.manager.add_entry("kubernetes", "另一个译名")

    def test_delete_entry(self) -> None:
        entry = self.manager.add_entry("Kubernetes", "K8s")
        self.assertTrue(self.manager.delete_entry(entry["id"]))
        self.assertEqual(self.manager.size, 0)

    def test_delete_entry_not_found(self) -> None:
        self.assertFalse(self.manager.delete_entry("nonexistent"))
        self.assertFalse(self.manager.delete_entry("bad id!"))

    def test_clear(self) -> None:
        self.manager.add_entry("A", "甲")
        self.manager.add_entry("B", "乙")
        self.assertEqual(self.manager.clear(), 2)
        self.assertEqual(self.manager.size, 0)

    def test_import_entries_deduplicates(self) -> None:
        self.manager.add_entry("Kubernetes", "K8s")
        imported = self.manager.import_entries([
            {"source": "Kubernetes", "target": "重复"},
            {"source": "Golang", "target": "Go 语言"},
        ])
        self.assertEqual(imported, 1)
        self.assertEqual(self.manager.size, 2)

    def test_import_csv_text(self) -> None:
        imported = self.manager.import_entries(
            "ML,机器学习\nLLM,大语言模型,true\n",
        )
        self.assertEqual(imported, 2)
        entries = self.manager.list_entries()
        llm = next(e for e in entries if e["source"] == "LLM")
        self.assertTrue(llm["keep_original"])

    def test_persists_across_instances(self) -> None:
        self.manager.add_entry("Kubernetes", "K8s")
        self.manager.add_entry("Golang", "Go 语言")

        reloaded = GlossaryManager(path=self.path)
        self.assertEqual(reloaded.size, 2)
        entries = reloaded.list_entries()
        self.assertEqual({e["source"] for e in entries}, {"Kubernetes", "Golang"})

    def test_loads_corrupt_file_as_empty(self) -> None:
        self.path.write_text("{ not valid json", encoding="utf-8")
        manager = GlossaryManager(path=self.path)
        self.assertEqual(manager.size, 0)

    def test_as_glossary_entries(self) -> None:
        self.manager.add_entry("Kubernetes", "K8s")
        entries = self.manager.as_glossary_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].source, "Kubernetes")
        self.assertEqual(entries[0].target, "K8s")

    def test_entry_id_is_stable_and_safe(self) -> None:
        entry = self.manager.add_entry("Hello, World!", "你好世界")
        self.assertEqual(entry["id"], "hello-world")


if __name__ == "__main__":
    unittest.main()
