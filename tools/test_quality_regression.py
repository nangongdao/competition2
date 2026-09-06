"""quality_regression.py 的单元测试：质量回归判断逻辑（纯函数）。"""

from __future__ import annotations

import unittest

from tools import quality_regression


class EvaluateRegressionTests(unittest.TestCase):
    def _base_bleu(self) -> dict:
        return {"corpus_bleu": 0.80, "avg_sentence_bleu": 0.81}

    def _base_wer(self) -> dict:
        return {"wer": 0.05, "cer": 0.02}

    def test_pass_when_scores_unchanged(self) -> None:
        result = quality_regression.evaluate_regression(
            bleu_report=self._base_bleu(),
            bleu_baseline=self._base_bleu(),
            asr_report=self._base_wer(),
            asr_baseline=self._base_wer(),
            bleu_threshold=0.05,
            wer_threshold=0.02,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["failures"], [])

    def test_pass_when_improved(self) -> None:
        result = quality_regression.evaluate_regression(
            bleu_report={"corpus_bleu": 0.85, "avg_sentence_bleu": 0.86},
            bleu_baseline=self._base_bleu(),
            asr_report={"wer": 0.03, "cer": 0.01},
            asr_baseline=self._base_wer(),
            bleu_threshold=0.05,
            wer_threshold=0.02,
        )
        self.assertTrue(result["ok"])

    def test_fail_when_bleu_drops_beyond_threshold(self) -> None:
        # 基线 0.80，允许相对下降 5% -> 0.04；当前 0.70 下降 0.10，超阈值。
        result = quality_regression.evaluate_regression(
            bleu_report={"corpus_bleu": 0.70, "avg_sentence_bleu": 0.71},
            bleu_baseline=self._base_bleu(),
            asr_report=self._base_wer(),
            asr_baseline=self._base_wer(),
            bleu_threshold=0.05,
            wer_threshold=0.02,
        )
        self.assertFalse(result["ok"])
        self.assertTrue(any("BLEU 回归" in f for f in result["failures"]))
        self.assertFalse(result["bleu"]["ok"])

    def test_pass_when_bleu_drop_within_threshold(self) -> None:
        # 基线 0.80，允许 5% -> 0.04；当前 0.78 下降 0.02，在阈值内。
        result = quality_regression.evaluate_regression(
            bleu_report={"corpus_bleu": 0.78, "avg_sentence_bleu": 0.79},
            bleu_baseline=self._base_bleu(),
            asr_report=self._base_wer(),
            asr_baseline=self._base_wer(),
            bleu_threshold=0.05,
            wer_threshold=0.02,
        )
        self.assertTrue(result["ok"])

    def test_fail_when_wer_rises_beyond_threshold(self) -> None:
        # 基线 WER 0.05，允许上升 0.02；当前 0.10 上升 0.05，超阈值。
        result = quality_regression.evaluate_regression(
            bleu_report=self._base_bleu(),
            bleu_baseline=self._base_bleu(),
            asr_report={"wer": 0.10, "cer": 0.05},
            asr_baseline=self._base_wer(),
            bleu_threshold=0.05,
            wer_threshold=0.02,
        )
        self.assertFalse(result["ok"])
        self.assertTrue(any("WER 回归" in f for f in result["failures"]))
        self.assertFalse(result["wer"]["ok"])

    def test_pass_when_wer_rise_within_threshold(self) -> None:
        result = quality_regression.evaluate_regression(
            bleu_report=self._base_bleu(),
            bleu_baseline=self._base_bleu(),
            asr_report={"wer": 0.06, "cer": 0.03},
            asr_baseline=self._base_wer(),
            bleu_threshold=0.05,
            wer_threshold=0.02,
        )
        self.assertTrue(result["ok"])

    def test_thresholds_are_relative_and_absolute_respectively(self) -> None:
        # BLEU 阈值是相对基线比例，WER 阈值是绝对上升量。
        result = quality_regression.evaluate_regression(
            bleu_report={"corpus_bleu": 0.79, "avg_sentence_bleu": 0.80},
            bleu_baseline=self._base_bleu(),
            asr_report=self._base_wer(),
            asr_baseline=self._base_wer(),
            bleu_threshold=0.05,
            wer_threshold=0.02,
        )
        # 0.80 -> 0.79 下降 0.01，允许 0.04，通过。
        self.assertTrue(result["ok"])
        self.assertAlmostEqual(result["bleu"]["allowed_drop"], 0.04)


if __name__ == "__main__":
    unittest.main()
