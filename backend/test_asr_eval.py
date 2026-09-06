"""Unit tests for the ASR quality evaluation (WER / CER)."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.asr_eval import (  # noqa: E402
    character_error_rate,
    edit_distance,
    evaluate,
    tokenize,
    word_error_rate,
)


class TokenizeTests(unittest.TestCase):
    def test_english_words(self) -> None:
        self.assertEqual(tokenize("hello world"), ["hello", "world"])

    def test_cjk_split_by_char(self) -> None:
        self.assertEqual(tokenize("你好世界"), ["你", "好", "世", "界"])

    def test_mixed(self) -> None:
        tokens = tokenize("你好 world 2026")
        self.assertIn("你", tokens)
        self.assertIn("world", tokens)
        self.assertIn("2026", tokens)

    def test_empty(self) -> None:
        self.assertEqual(tokenize(""), [])
        self.assertEqual(tokenize("   "), [])

    def test_punctuation_kept(self) -> None:
        self.assertEqual(tokenize("hello, world!"), ["hello,", "world!"])


class EditDistanceTests(unittest.TestCase):
    def test_identical_zero(self) -> None:
        self.assertEqual(edit_distance(["a", "b", "c"], ["a", "b", "c"]), 0)

    def test_substitution(self) -> None:
        self.assertEqual(edit_distance(["a", "b"], ["a", "c"]), 1)

    def test_insertion(self) -> None:
        self.assertEqual(edit_distance(["a"], ["a", "b"]), 1)

    def test_deletion(self) -> None:
        self.assertEqual(edit_distance(["a", "b"], ["a"]), 1)

    def test_empty_left(self) -> None:
        self.assertEqual(edit_distance([], ["a", "b"]), 2)

    def test_empty_right(self) -> None:
        self.assertEqual(edit_distance(["a", "b"], []), 2)

    def test_both_empty(self) -> None:
        self.assertEqual(edit_distance([], []), 0)

    def test_real_example(self) -> None:
        # "kitten" -> "sitting"：3 次编辑
        self.assertEqual(
            edit_distance(list("kitten"), list("sitting")), 3
        )


class WordErrorRateTests(unittest.TestCase):
    def test_identical_zero(self) -> None:
        self.assertEqual(word_error_rate("hello world", "hello world"), 0.0)

    def test_one_substitution(self) -> None:
        # "cat" 替换为 "dog"，2 词参考中 1 词错误 -> 0.5
        self.assertEqual(word_error_rate("a cat", "a dog"), 0.5)

    def test_one_insertion(self) -> None:
        # 多插入一个词 -> 编辑距离 1 / 参考 2 = 0.5
        self.assertEqual(word_error_rate("a b", "a x b"), 0.5)

    def test_total_error(self) -> None:
        # 候选完全不同
        self.assertEqual(word_error_rate("hello world", "completely different"), 1.0)

    def test_empty_reference(self) -> None:
        self.assertEqual(word_error_rate("", "hello"), 1.0)
        self.assertEqual(word_error_rate("", ""), 0.0)

    def test_accuracy_direction(self) -> None:
        # WER 越低越准：完全匹配应低于部分错误。
        low = word_error_rate("the cat sits", "the dog runs")
        high = word_error_rate("the cat sits", "the cat sits")
        self.assertLess(high, low)


class CharacterErrorRateTests(unittest.TestCase):
    def test_identical_zero(self) -> None:
        self.assertEqual(character_error_rate("你好世界", "你好世界"), 0.0)

    def test_one_char_substitution(self) -> None:
        # 4 字符中 1 字符错 -> 0.25
        self.assertEqual(character_error_rate("你好世界", "你坏世界"), 0.25)

    def test_empty_reference(self) -> None:
        self.assertEqual(character_error_rate("", "你好"), 1.0)
        self.assertEqual(character_error_rate("", ""), 0.0)

    def test_wer_and_cer_align_on_english(self) -> None:
        # 英文句子词级与字符级错误率都可计算，字符级通常小于等于词级。
        wer = word_error_rate("the cat sits", "the dog sits")
        cer = character_error_rate("the cat sits", "the dog sits")
        self.assertLessEqual(cer, wer)


class EvaluateTests(unittest.TestCase):
    def test_empty_inputs(self) -> None:
        report = evaluate([], [])
        self.assertEqual(report.num_pairs, 0)
        self.assertEqual(report.word_error_rate, 0.0)

    def test_identical_corpus(self) -> None:
        report = evaluate(
            ["hello world", "the cat sits"],
            ["hello world", "the cat sits"],
        )
        self.assertEqual(report.word_error_rate, 0.0)
        self.assertEqual(report.word_accuracy, 1.0)
        self.assertEqual(report.num_pairs, 2)

    def test_mismatched_length_raises(self) -> None:
        with self.assertRaises(ValueError):
            evaluate(["a"], ["a", "b"])

    def test_partial_corpus(self) -> None:
        # 2 参考词中 1 错 + 1 参考词全对 -> 总编辑 1 / 参考 3
        report = evaluate(
            ["a cat", "dog"],
            ["a dog", "dog"],
        )
        self.assertAlmostEqual(report.word_error_rate, 1 / 3, places=4)
        self.assertAlmostEqual(report.word_accuracy, 1 - 1 / 3, places=4)

    def test_to_dict_fields(self) -> None:
        report = evaluate(["hello world"], ["hello world"])
        d = report.to_dict()
        self.assertIn("wer", d)
        self.assertIn("cer", d)
        self.assertIn("word_accuracy", d)
        self.assertIn("character_accuracy", d)
        self.assertEqual(d["num_pairs"], 1)


if __name__ == "__main__":
    unittest.main()


class ToolIntegrationTests(unittest.TestCase):
    """对 tools/eval_translation_quality.py 的 --wer 路径做集成验证。"""

    TOOL = Path(__file__).resolve().parents[1] / "tools" / "eval_translation_quality.py"

    def _run_tool(self, csv_path: Path, *extra: str) -> str:
        import subprocess

        result = subprocess.run(
            [sys.executable, str(self.TOOL), "--pair-file", str(csv_path), *extra],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        return result.stdout

    def test_wer_json_output(self) -> None:
        csv_path = Path(__file__).resolve().parent / "_tmp_asr_eval.csv"
        try:
            csv_path.write_text(
                "hello world,hello world\n"
                "the cat sits,the dog sits\n",
                encoding="utf-8",
            )
            out = self._run_tool(csv_path, "--wer", "--json")
            import json

            data = json.loads(out)
            self.assertEqual(data["pairs"], 2)
            self.assertIn("wer", data)
            self.assertIn("cer", data)
            self.assertIn("word_accuracy", data)
            self.assertAlmostEqual(data["word_accuracy"], 1.0 - data["wer"], places=4)
        finally:
            if csv_path.exists():
                csv_path.unlink()

    def test_wer_text_output(self) -> None:
        csv_path = Path(__file__).resolve().parent / "_tmp_asr_eval2.csv"
        try:
            csv_path.write_text(
                "the quick brown fox, the quick brown fox\n",
                encoding="utf-8",
            )
            out = self._run_tool(csv_path, "--wer")
            self.assertIn("WER", out)
            self.assertIn("词级准确率", out)
            self.assertIn("0.0000", out)  # 完全匹配 -> WER 0
        finally:
            if csv_path.exists():
                csv_path.unlink()

    def test_wer_missing_file_fails(self) -> None:
        import subprocess

        missing = Path(__file__).resolve().parent / "_no_such_file.csv"
        result = subprocess.run(
            [sys.executable, str(self.TOOL), "--pair-file", str(missing), "--wer"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertNotEqual(result.returncode, 0)
