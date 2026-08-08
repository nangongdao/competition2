"""Unit tests for the layered context window formatting."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from models.segment import ContextWindow, Segment, compress_text


def make_segment(index: int, text: str) -> Segment:
    return Segment(
        id=f"session-{index}",
        text_asr=text,
        confidence=0.9,
        source_language="en",
        target_language="zh-CN",
        text_translated=f"译{index}",
    )


class CompressTextTests(unittest.TestCase):
    def test_short_text_unchanged(self) -> None:
        self.assertEqual(compress_text("hello", 40), "hello")

    def test_long_text_truncated_with_ellipsis(self) -> None:
        result = compress_text("a" * 100, 40)
        self.assertEqual(len(result), 41)
        self.assertTrue(result.endswith("…"))
        self.assertTrue(result.startswith("a" * 40))

    def test_non_positive_limit_returns_text(self) -> None:
        self.assertEqual(compress_text("hello", 0), "hello")


class LayeredContextTests(unittest.TestCase):
    def test_recent_sentences_keep_full_text(self) -> None:
        window = ContextWindow(session_id="s", window_size=10)
        for index in range(5):
            window.add_segment(make_segment(index, f"full sentence {index}"))

        text = window.to_context_text(
            max_sentences=10,
            recent_sentences=3,
            older_max_chars=40,
        )

        # 最近 3 句（index 2,3,4）原文完整出现
        self.assertIn("full sentence 2", text)
        self.assertIn("full sentence 3", text)
        self.assertIn("full sentence 4", text)
        # 早句（index 0,1）未超压缩阈值时也保留，但位于 recent 之前（older 在前）
        self.assertLess(text.find("full sentence 0"), text.find("full sentence 2"))

    def test_older_sentences_truncated_to_max_chars(self) -> None:
        window = ContextWindow(session_id="s", window_size=10)
        window.add_segment(make_segment(0, "x" * 80))  # 超长早句
        window.add_segment(make_segment(1, "recent one"))

        text = window.to_context_text(
            max_sentences=10,
            recent_sentences=1,
            older_max_chars=10,
        )

        self.assertIn("x" * 10, text)
        self.assertNotIn("x" * 11, text)
        self.assertIn("…", text)
        # 最近句保持完整
        self.assertIn("recent one", text)

    def test_max_sentences_budget_split_between_older_and_recent(self) -> None:
        window = ContextWindow(session_id="s", window_size=10)
        for index in range(6):
            window.add_segment(make_segment(index, f"sentence {index}"))

        text = window.to_context_text(
            max_sentences=4,
            recent_sentences=3,
            older_max_chars=20,
        )

        # 4 句预算：3 句 recent + 1 句 older（index 2）
        self.assertIn("sentence 2", text)
        self.assertIn("sentence 3", text)
        self.assertIn("sentence 4", text)
        self.assertIn("sentence 5", text)
        # index 0/1 超出预算被排除
        self.assertNotIn("sentence 0", text)
        self.assertNotIn("sentence 1", text)

    def test_summary_prepended_when_present(self) -> None:
        window = ContextWindow(session_id="s", window_size=10, summary="早前摘要。")
        for index in range(2):
            window.add_segment(make_segment(index, f"later {index}"))

        text = window.to_context_text(max_sentences=10, recent_sentences=2, older_max_chars=40)

        self.assertTrue(text.startswith("早前摘要。"))

    def test_empty_window_returns_empty(self) -> None:
        window = ContextWindow(session_id="s")
        self.assertEqual(window.to_context_text(), "")


if __name__ == "__main__":
    unittest.main()
