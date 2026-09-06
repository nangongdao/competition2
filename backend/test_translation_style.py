"""Tests for translation style presets (ROADMAP Phase 3)."""

from __future__ import annotations

import unittest

from services.translation_style import (
    DEFAULT_STYLE_PRESET,
    STYLE_PRESETS,
    normalize_style_preset,
    style_preset_instruction,
)


class NormalizeStylePresetTests(unittest.TestCase):
    def test_default_is_concise(self) -> None:
        self.assertEqual(DEFAULT_STYLE_PRESET, "concise")

    def test_accepts_canonical_presets(self) -> None:
        for key in STYLE_PRESETS:
            self.assertEqual(normalize_style_preset(key), key)

    def test_case_insensitive(self) -> None:
        self.assertEqual(normalize_style_preset("CONCISE"), "concise")
        self.assertEqual(normalize_style_preset("Faithful"), "faithful")
        self.assertEqual(normalize_style_preset("Lecture"), "lecture")

    def test_aliases_map_to_canonical(self) -> None:
        self.assertEqual(normalize_style_preset("brief"), "concise")
        self.assertEqual(normalize_style_preset("literal"), "faithful")
        self.assertEqual(normalize_style_preset("summary"), "lecture")
        self.assertEqual(normalize_style_preset("lecture-notes"), "lecture")

    def test_unknown_falls_back_to_default(self) -> None:
        self.assertEqual(normalize_style_preset("fancy"), DEFAULT_STYLE_PRESET)
        self.assertEqual(normalize_style_preset(""), DEFAULT_STYLE_PRESET)
        self.assertEqual(normalize_style_preset(None), DEFAULT_STYLE_PRESET)
        self.assertEqual(normalize_style_preset(123), DEFAULT_STYLE_PRESET)


class StylePresetInstructionTests(unittest.TestCase):
    def test_default_returns_empty_instruction(self) -> None:
        # 默认风格不注入额外指令，保持与历史行为一致
        self.assertEqual(style_preset_instruction("concise"), "")

    def test_faithful_injects_instruction(self) -> None:
        instruction = style_preset_instruction("faithful")
        self.assertIn("FAITHFUL", instruction)
        self.assertIn("preserving", instruction)

    def test_lecture_injects_instruction(self) -> None:
        instruction = style_preset_instruction("lecture")
        self.assertIn("LECTURE NOTES", instruction)
        self.assertIn("study value", instruction)

    def test_unknown_style_returns_empty(self) -> None:
        self.assertEqual(style_preset_instruction("unknown-style"), "")


if __name__ == "__main__":
    unittest.main()
