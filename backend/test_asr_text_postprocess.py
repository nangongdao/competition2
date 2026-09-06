"""ASR 文本后处理模块测试（阶段 2：标点/空白/大小写恢复）。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.asr_text_postprocess import (  # noqa: E402
    collapse_whitespace,
    ensure_sentence_ending,
    normalize_cjk_spacing,
    normalize_numbers,
    postprocess_asr_text,
    restore_sentence_capitalization,
)


class CollapseWhitespaceTests(unittest.TestCase):
    def test_collapses_multiple_spaces(self) -> None:
        self.assertEqual(collapse_whitespace("hello   world"), "hello world")

    def test_collapses_newlines_and_tabs(self) -> None:
        self.assertEqual(collapse_whitespace("hello\n\t world"), "hello world")

    def test_strips_leading_trailing(self) -> None:
        self.assertEqual(collapse_whitespace("  hello world  "), "hello world")

    def test_empty_input(self) -> None:
        self.assertEqual(collapse_whitespace(""), "")
        self.assertEqual(collapse_whitespace("   "), "")


class EnsureSentenceEndingTests(unittest.TestCase):
    def test_appends_period_to_english(self) -> None:
        self.assertEqual(ensure_sentence_ending("Hello world"), "Hello world.")

    def test_keeps_existing_punctuation(self) -> None:
        self.assertEqual(ensure_sentence_ending("Hello world!"), "Hello world!")
        self.assertEqual(ensure_sentence_ending("Hello world?"), "Hello world?")

    def test_appends_chinese_period(self) -> None:
        self.assertEqual(ensure_sentence_ending("你好世界"), "你好世界。")

    def test_keeps_chinese_punctuation(self) -> None:
        self.assertEqual(ensure_sentence_ending("你好世界！"), "你好世界！")

    def test_does_not_append_to_partial(self) -> None:
        # 以括号/省略号结尾不强行补句号
        self.assertEqual(ensure_sentence_ending("..." ), "...")
        self.assertEqual(ensure_sentence_ending("Hello"), "Hello.")


class NormalizeCjkSpacingTests(unittest.TestCase):
    def test_removes_space_between_chinese_and_punct(self) -> None:
        self.assertEqual(normalize_cjk_spacing("你好 ，世界"), "你好，世界")

    def test_keeps_space_between_chinese_and_english(self) -> None:
        self.assertEqual(normalize_cjk_spacing("使用 AI 助手"), "使用 AI 助手")

    def test_adds_space_after_comma_between_english_words(self) -> None:
        self.assertEqual(normalize_cjk_spacing("hello,world"), "hello, world")

    def test_empty_input(self) -> None:
        self.assertEqual(normalize_cjk_spacing(""), "")


class RestoreCapitalizationTests(unittest.TestCase):
    def test_capitalizes_sentence_start(self) -> None:
        self.assertEqual(restore_sentence_capitalization("hello world"), "Hello world")

    def test_capitalizes_after_period(self) -> None:
        self.assertEqual(
            restore_sentence_capitalization("Hello world. good morning"),
            "Hello world. Good morning",
        )

    def test_skips_cjk(self) -> None:
        self.assertEqual(restore_sentence_capitalization("你好世界。再见"), "你好世界。再见")

    def test_does_not_lowercase_proper_nouns(self) -> None:
        self.assertEqual(
            restore_sentence_capitalization("Kubernetes and docker"),
            "Kubernetes and docker",
        )


class PostprocessAsrTextTests(unittest.TestCase):
    def test_full_pipeline_english(self) -> None:
        self.assertEqual(
            postprocess_asr_text("  hello   world  ", language="en"),
            "Hello world.",
        )

    def test_full_pipeline_chinese(self) -> None:
        self.assertEqual(
            postprocess_asr_text("你好  世界", language="zh-CN"),
            "你好世界。",
        )

    def test_empty_input_passthrough(self) -> None:
        self.assertEqual(postprocess_asr_text(""), "")
        self.assertEqual(postprocess_asr_text("   "), "   ")

    def test_japanese_does_not_capitalize(self) -> None:
        # 日语为 latin 判断外，不应强行补英文句号/大写
        result = postprocess_asr_text("こんにちは 世界", language="ja")
        self.assertNotIn(".", result)

    def test_keeps_technical_terms(self) -> None:
        result = postprocess_asr_text("we use Kubernetes and Docker", language="en")
        self.assertIn("Kubernetes", result)
        self.assertIn("Docker", result)


class NormalizeNumbersTests(unittest.TestCase):
    def test_converts_fullwidth_digits(self) -> None:
        self.assertEqual(normalize_numbers("总量达到１２３４５６"), "总量达到123456")

    def test_removes_space_before_percent(self) -> None:
        self.assertEqual(normalize_numbers("accuracy is 50 %"), "accuracy is 50%")

    def test_keeps_decimal_and_thousands(self) -> None:
        self.assertEqual(normalize_numbers("1,234.56"), "1,234.56")

    def test_fullwidth_decimal_and_thousands_separator(self) -> None:
        self.assertEqual(normalize_numbers("１，２３４．５６"), "1,234.56")

    def test_keeps_currency_prefix(self) -> None:
        self.assertEqual(normalize_numbers("$1.2M revenue"), "$1.2M revenue")

    def test_does_not_round_or_alter_value(self) -> None:
        # 只做格式统一，不改数值
        self.assertEqual(normalize_numbers("3.5 GHz"), "3.5 GHz")
        self.assertEqual(normalize_numbers("2026"), "2026")

    def test_empty_input(self) -> None:
        self.assertEqual(normalize_numbers(""), "")
        self.assertEqual(normalize_numbers("hello world"), "hello world")

    def test_pipeline_normalizes_numbers(self) -> None:
        result = postprocess_asr_text("The cost is ５０ % and the year is ２０２６", language="en")
        self.assertIn("50%", result)
        self.assertIn("2026", result)
        self.assertNotIn("５", result)


if __name__ == "__main__":
    unittest.main()
