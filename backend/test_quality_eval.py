"""Unit tests for the lightweight translation quality evaluation (轻量 BLEU)."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.quality_eval import (  # noqa: E402
    corpus_bleu,
    evaluate,
    sentence_bleu,
    tokenize,
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


class SentenceBleuTests(unittest.TestCase):
    def test_identical_high_score(self) -> None:
        score = sentence_bleu("the cat sits on the mat", "the cat sits on the mat")
        self.assertGreaterEqual(score, 0.99)

    def test_unrelated_low_score(self) -> None:
        score = sentence_bleu("hello world", "completely different text here")
        self.assertLess(score, 0.5)

    def test_empty_candidate_zero(self) -> None:
        self.assertEqual(sentence_bleu("hello world", ""), 0.0)
        self.assertEqual(sentence_bleu("", "hello"), 0.0)

    def test_chinese_identical(self) -> None:
        score = sentence_bleu("你好世界", "你好世界")
        self.assertGreaterEqual(score, 0.9)

    def test_partial_overlap_between(self) -> None:
        low = sentence_bleu("a b c d", "a b x y")
        high = sentence_bleu("a b c d", "a b c d")
        self.assertLess(low, high)


class CorpusBleuTests(unittest.TestCase):
    def test_identical_corpus_high(self) -> None:
        refs = ["hello world", "the cat sits"]
        cands = ["hello world", "the cat sits"]
        self.assertGreaterEqual(corpus_bleu(refs, cands), 0.99)

    def test_empty_corpus_zero(self) -> None:
        self.assertEqual(corpus_bleu([], []), 0.0)

    def test_mismatched_length_raises(self) -> None:
        with self.assertRaises(ValueError):
            corpus_bleu(["a"], ["a", "b"])

    def test_partial_corpus(self) -> None:
        refs = ["the cat sits on the mat", "hello world"]
        cands = ["the cat sits on the mat", "hello world"]
        self.assertGreaterEqual(corpus_bleu(refs, cands), 0.99)


class EvaluateTests(unittest.TestCase):
    def test_report_fields(self) -> None:
        report = evaluate(["hello world"], ["hello world"])
        self.assertEqual(report.num_pairs, 1)
        self.assertGreaterEqual(report.corpus_bleu, 0.99)
        self.assertEqual(len(report.sentence_scores), 1)
        self.assertAlmostEqual(report.avg_sentence_bleu, report.sentence_scores[0], places=6)

    def test_to_dict(self) -> None:
        report = evaluate(["a b"], ["a b"])
        d = report.to_dict()
        self.assertIn("corpus_bleu", d)
        self.assertIn("avg_sentence_bleu", d)
        self.assertIn("num_pairs", d)

    def test_mismatch_raises(self) -> None:
        with self.assertRaises(ValueError):
            evaluate(["a"], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
