"""Unit tests for the glossary and domain-adaptation prompt builder."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.glossary import (
    GlossaryEntry,
    build_glossary_prompt,
    parse_glossary_csv,
    parse_glossary_json,
)


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


if __name__ == "__main__":
    unittest.main()
