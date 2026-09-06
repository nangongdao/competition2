"""Unit tests for the glossary and domain-adaptation prompt builder."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


BACKEND_ROOT = Path(__file__).resolve().parent

# 直接按文件加载 glossary 模块，避免触发 services/__init__.py 的重依赖导入链。
# glossary.py 是纯标准库实现，可零重依赖运行。
import importlib.util

_glossary_path = BACKEND_ROOT / "services" / "glossary.py"
_spec = importlib.util.spec_from_file_location("glossary", _glossary_path)
_glossary = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["glossary"] = _glossary
_spec.loader.exec_module(_glossary)

GlossaryEntry = _glossary.GlossaryEntry
build_glossary_prompt = _glossary.build_glossary_prompt
normalize_glossary_entries = _glossary.normalize_glossary_entries
parse_glossary_csv = _glossary.parse_glossary_csv
parse_glossary_json = _glossary.parse_glossary_json


class GlossaryPromptTests(unittest.TestCase):
    def test_empty_glossary_returns_empty_prompt(self) -> None:
        self.assertEqual(build_glossary_prompt([], "Some text"), "")

    def test_no_hit_returns_empty_prompt(self) -> None:
        glossary = [GlossaryEntry(source="Kubernetes", target="K8s")]
        self.assertEqual(build_glossary_prompt(glossary, "Hello world"), "")

    def test_only_hit_entries_injected(self) -> None:
        glossary = [
            GlossaryEntry(source="Kubernetes", target="容器编排平台"),
            GlossaryEntry(source="Golang", target="Go 语言"),
        ]
        prompt = build_glossary_prompt(glossary, "We run Kubernetes in production")

        self.assertIn("Kubernetes", prompt)
        self.assertIn("容器编排平台", prompt)
        self.assertNotIn("Golang", prompt)

    def test_hit_is_case_insensitive(self) -> None:
        glossary = [GlossaryEntry(source="kubernetes", target="K8s")]
        prompt = build_glossary_prompt(glossary, "Using KUBERNETES today")

        self.assertIn("kubernetes", prompt)

    def test_keep_original_renders_as_keep_instruction(self) -> None:
        glossary = [GlossaryEntry(source="Kubernetes", target="", keep_original=True)]
        prompt = build_glossary_prompt(glossary, "Kubernetes is great")

        self.assertIn("保持原文", prompt)


class GlossaryParserTests(unittest.TestCase):
    def test_parse_json_array(self) -> None:
        entries = parse_glossary_json([
            {"source": "K8s", "target": "Kubernetes"},
            {"source": "ML", "target": "机器学习", "keep_original": True},
        ])

        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].source, "K8s")
        self.assertEqual(entries[0].target, "Kubernetes")
        self.assertFalse(entries[0].keep_original)
        self.assertTrue(entries[1].keep_original)

    def test_parse_json_wrapped_entries(self) -> None:
        entries = parse_glossary_json({"entries": [{"source": "K8s", "target": "Kubernetes"}]})
        self.assertEqual(len(entries), 1)

    def test_parse_json_ignores_invalid_items(self) -> None:
        entries = parse_glossary_json([
            {"source": "K8s", "target": "Kubernetes"},
            {"source": 123, "target": "bad"},
            "not-a-dict",
            {},
        ])
        self.assertEqual(len(entries), 1)

    def test_parse_json_non_list_returns_empty(self) -> None:
        self.assertEqual(parse_glossary_json("nope"), [])
        self.assertEqual(parse_glossary_json(None), [])

    def test_parse_csv_three_columns(self) -> None:
        entries = parse_glossary_csv(
            "K8s,Kubernetes,true\nML,机器学习\n\n# comment would need handling\n"
        )

        self.assertEqual(len(entries), 2)
        self.assertTrue(entries[0].keep_original)
        self.assertFalse(entries[1].keep_original)
        self.assertEqual(entries[1].target, "机器学习")

    def test_parse_csv_skips_blank_rows(self) -> None:
        entries = parse_glossary_csv("K8s,Kubernetes\n\n , \n")
        self.assertEqual(len(entries), 1)


class GlossaryNormalizeTests(unittest.TestCase):
    """术语归一化与去重回归矩阵（方向 10）。"""

    def test_empty_input_returns_empty(self) -> None:
        self.assertEqual(normalize_glossary_entries([]), [])

    def test_blank_source_dropped(self) -> None:
        entries = [
            GlossaryEntry(source="   ", target="x"),
            GlossaryEntry(source="", target="y"),
            GlossaryEntry(source="K8s", target="Kubernetes"),
        ]
        result = normalize_glossary_entries(entries)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].source, "K8s")

    def test_overlong_source_dropped(self) -> None:
        long_term = "a" * 100
        entries = [
            GlossaryEntry(source=long_term, target="drop"),
            GlossaryEntry(source="K8s", target="Kubernetes"),
        ]
        result = normalize_glossary_entries(entries, max_term_length=64)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].source, "K8s")

    def test_case_insensitive_dedup_later_wins_target(self) -> None:
        entries = [
            GlossaryEntry(source="Kubernetes", target="旧译"),
            GlossaryEntry(source="kubernetes", target="新译"),
        ]
        result = normalize_glossary_entries(entries)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].source, "Kubernetes")
        self.assertEqual(result[0].target, "新译")

    def test_keep_original_merged_from_any_entry(self) -> None:
        entries = [
            GlossaryEntry(source="ML", target="机器学习", keep_original=False),
            GlossaryEntry(source="ml", target="", keep_original=True),
        ]
        result = normalize_glossary_entries(entries)
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].keep_original)

    def test_keep_original_survives_later_overwrite(self) -> None:
        entries = [
            GlossaryEntry(source="ML", target="", keep_original=True),
            GlossaryEntry(source="ml", target="机器学习"),
        ]
        result = normalize_glossary_entries(entries)
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].keep_original)
        self.assertEqual(result[0].target, "机器学习")

    def test_max_entries_truncates_stably(self) -> None:
        entries = [GlossaryEntry(source=f"term-{index}", target="t") for index in range(10)]
        result = normalize_glossary_entries(entries, max_entries=3)
        self.assertEqual(len(result), 3)
        self.assertEqual([entry.source for entry in result], ["term-0", "term-1", "term-2"])

    def test_order_stable_and_distinct(self) -> None:
        entries = [
            GlossaryEntry(source="B", target="1"),
            GlossaryEntry(source="A", target="2"),
            GlossaryEntry(source="C", target="3"),
        ]
        result = normalize_glossary_entries(entries)
        self.assertEqual([entry.source for entry in result], ["B", "A", "C"])


if __name__ == "__main__":
    unittest.main()
