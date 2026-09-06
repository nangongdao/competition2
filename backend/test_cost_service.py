"""Unit tests for the cost model service (商用成本模型)."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.cost_service import (  # noqa: E402
    CostService,
    CostUsage,
    _estimate_cost,
    estimate_tokens,
)


class EstimateTokenTests(unittest.TestCase):
    def test_empty_returns_zero(self) -> None:
        self.assertEqual(estimate_tokens(""), 0)

    def test_latin_roughly_four_chars_per_token(self) -> None:
        # 40 个拉丁字符 ≈ 10 token
        text = "hello world this is a test sentence with words"
        tokens = estimate_tokens(text)
        self.assertGreaterEqual(tokens, 1)
        self.assertLessEqual(tokens, len(text))

    def test_cjk_roughly_one_and_half_chars_per_token(self) -> None:
        # 9 个汉字 ≈ 6 token
        text = "你好世界你好世界你好"
        tokens = estimate_tokens(text)
        self.assertGreaterEqual(tokens, 1)

    def test_mixed_cjk_and_latin(self) -> None:
        text = "你好 world 2026"
        tokens = estimate_tokens(text)
        self.assertGreaterEqual(tokens, 1)


class CostUsageTests(unittest.TestCase):
    def test_add_accumulates(self) -> None:
        a = CostUsage(nmt_input_tokens=10, nmt_output_tokens=5, asr_seconds=2.0, tts_chars=20)
        b = CostUsage(nmt_input_tokens=5, nmt_output_tokens=5, asr_seconds=1.0, tts_chars=10)
        a.add(b)
        self.assertEqual(a.nmt_input_tokens, 15)
        self.assertEqual(a.nmt_output_tokens, 10)
        self.assertAlmostEqual(a.asr_seconds, 3.0)
        self.assertEqual(a.tts_chars, 30)

    def test_to_dict_rounds_asr_seconds(self) -> None:
        usage = CostUsage(asr_seconds=2.3333)
        self.assertEqual(usage.to_dict()["asr_seconds"], 2.333)


class EstimateCostTests(unittest.TestCase):
    def test_cost_is_zero_for_no_usage(self) -> None:
        usage = CostUsage()
        self.assertEqual(_estimate_cost(usage, 0.15, 0.60), 0.0)

    def test_nmt_cost_positive(self) -> None:
        usage = CostUsage(nmt_input_tokens=1_000_000, nmt_output_tokens=1_000_000)
        cost = _estimate_cost(usage, 0.15, 0.60)
        # 1M in * 0.15 + 1M out * 0.60 = 0.75
        self.assertAlmostEqual(cost, 0.75, places=6)

    def test_asr_cost_per_minute(self) -> None:
        usage = CostUsage(asr_seconds=60.0)
        cost = _estimate_cost(usage, 0.15, 0.60)
        # 60s = 1 分钟 * 0.006 = 0.006
        self.assertAlmostEqual(cost, 0.006, places=6)

    def test_tts_cost_per_k_chars(self) -> None:
        usage = CostUsage(tts_chars=1000)
        cost = _estimate_cost(usage, 0.15, 0.60)
        # 1000 chars / 1000 * 0.015 = 0.015
        self.assertAlmostEqual(cost, 0.015, places=6)


class CostServiceTests(unittest.TestCase):
    def _make_service(self) -> tuple[CostService, Path]:
        temp_dir = tempfile.mkdtemp()
        path = Path(temp_dir) / "cost.json"
        return CostService(path=path), path

    def test_record_accumulates_and_persists(self) -> None:
        service, path = self._make_service()
        service.record(CostUsage(nmt_input_tokens=100, nmt_output_tokens=50))
        service.record(CostUsage(nmt_input_tokens=100, nmt_output_tokens=50))
        snap = service.snapshot()
        self.assertEqual(snap["usage"]["nmt_input_tokens"], 200)
        self.assertEqual(snap["usage"]["nmt_output_tokens"], 100)
        self.assertTrue(path.exists())

    def test_persist_then_reload(self) -> None:
        service, path = self._make_service()
        service.record(CostUsage(nmt_input_tokens=100, nmt_output_tokens=50), is_new_session=True)
        # 重新加载
        service2 = CostService(path=path)
        snap = service2.snapshot()
        self.assertEqual(snap["total_sessions"], 1)
        self.assertEqual(snap["usage"]["nmt_input_tokens"], 100)

    def test_reset_clears(self) -> None:
        service, _ = self._make_service()
        service.record(CostUsage(nmt_input_tokens=100))
        snap = service.reset()
        self.assertEqual(snap["usage"]["nmt_input_tokens"], 0)
        self.assertEqual(snap["total_sessions"], 0)

    def test_cost_limit_suggestion(self) -> None:
        service, _ = self._make_service()
        # 大量 NMT token 使成本超过软上限（默认 $2）
        service.record(CostUsage(nmt_input_tokens=10_000_000, nmt_output_tokens=2_000_000))
        snap = service.snapshot()
        self.assertGreaterEqual(snap["today_cost_usd"], snap["daily_cost_limit_usd"])
        self.assertTrue(snap["suggestions"])

    def test_corrupt_file_falls_back(self) -> None:
        temp_dir = tempfile.mkdtemp()
        path = Path(temp_dir) / "cost.json"
        path.write_text("{ not valid json", encoding="utf-8")
        service = CostService(path=path)
        snap = service.snapshot()
        self.assertEqual(snap["total_sessions"], 0)
        self.assertEqual(snap["usage"]["nmt_input_tokens"], 0)

    def test_estimate_note_present(self) -> None:
        service, _ = self._make_service()
        snap = service.snapshot()
        self.assertIn("token_estimate_note", snap)


if __name__ == "__main__":
    unittest.main()
