import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from models.segment import ContextWindow, Segment
from services.asr_service import ASRDecodeResult
from services.revision_service import RevisionService


class FakeNMTService:
    def __init__(self, translation: str, completion: str = "CORRECT") -> None:
        self.translation = translation
        self.completion = completion
        self.translation_calls = 0
        self.completion_calls = 0
        self.last_system_prompt = ""

    async def translate_stream(self, _context: ContextWindow, _segment: Segment):
        self.translation_calls += 1
        yield self.translation
        yield "<FINAL>"

    async def complete_text(self, _prompt: str, *, system_prompt: str) -> str:
        self.completion_calls += 1
        self.last_system_prompt = system_prompt
        assert "ASR post-editor" in system_prompt
        return self.completion


class FakeASRService:
    def __init__(
        self,
        payload: bytes = b"audio",
        redecode_result: ASRDecodeResult | None = None,
    ) -> None:
        self.payload = payload
        self.redecode_result = redecode_result
        self.redecode_calls = 0
        self.last_redecode_payload: bytes | None = None

    def get_last_audio_chunk(self) -> bytes:
        return self.payload

    async def redecode_audio(self, audio_bytes: bytes) -> ASRDecodeResult | None:
        self.redecode_calls += 1
        self.last_redecode_payload = audio_bytes
        return self.redecode_result


class RevisionServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_translation_revision_returns_translation_correction(self) -> None:
        service = RevisionService()
        context = ContextWindow(session_id="s1", window_size=10)
        context.add_segment(Segment(
            id="s1_0",
            text_asr="hello",
            confidence=0.95,
            text_translated="old hello",
        ))
        context.add_segment(Segment(
            id="s1_1",
            text_asr="world",
            confidence=0.95,
            text_translated="old world",
        ))
        context.add_segment(Segment(
            id="s1_2",
            text_asr="today",
            confidence=0.95,
            text_translated="today",
        ))

        results = await service.check_and_revise(
            context,
            FakeNMTService("completely different translation"),
            force=True,
            trigger_segment=context.get_all()[-1],
            trigger="manual",
        )

        self.assertEqual(len(results), 2)
        self.assertTrue(all(item.reason == "translation_correction" for item in results))
        self.assertTrue(all(item.source_text is None for item in results))
        self.assertTrue(all(item.correction_source == "translation_window" for item in results))
        self.assertTrue(all(item.trigger == "manual" for item in results))
        self.assertTrue(all(item.old_text for item in results))

    async def test_asr_correction_returns_source_and_translation(self) -> None:
        service = RevisionService()
        context = ContextWindow(session_id="s2", window_size=10)
        context.add_segment(Segment(
            id="s2_0",
            text_asr="previous sentence",
            confidence=0.95,
            text_translated="previous translation",
        ))
        segment = Segment(
            id="s2_1",
            text_asr="grain sand",
            confidence=-1.2,
            text_translated="wrong translation",
        )
        context.add_segment(segment)

        result = await service.check_asr_correction(
            segment,
            context,
            FakeNMTService("corrected translation", completion="great sentence"),
            FakeASRService(),
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.reason, "asr_correction")
        self.assertEqual(result.source_text, "great sentence")
        self.assertEqual(result.new_text, "corrected translation")
        self.assertEqual(result.correction_source, "llm_post_edit")
        self.assertEqual(result.old_text, "wrong translation")
        self.assertEqual(result.old_source_text, "grain sand")

    async def test_asr_correction_prefers_audio_redecode(self) -> None:
        service = RevisionService()
        context = ContextWindow(session_id="s3", window_size=10)
        segment = Segment(
            id="s3_0",
            text_asr="grain sand",
            confidence=-1.2,
            text_translated="wrong translation",
        )
        context.add_segment(segment)
        nmt = FakeNMTService("corrected translation", completion="should not be used")
        asr = FakeASRService(
            redecode_result=ASRDecodeResult(text="great sentence", confidence=-0.2),
        )

        result = await service.check_asr_correction(
            segment,
            context,
            nmt,
            asr,
            audio_chunk=b"cached-audio",
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(asr.redecode_calls, 1)
        self.assertEqual(asr.last_redecode_payload, b"cached-audio")
        self.assertEqual(nmt.completion_calls, 0)
        self.assertEqual(result.reason, "asr_correction")
        self.assertEqual(result.source_text, "great sentence")
        self.assertEqual(result.new_text, "corrected translation")
        self.assertEqual(result.old_text, "wrong translation")
        self.assertEqual(result.old_source_text, "grain sand")
        self.assertEqual(result.correction_source, "audio_redecode")
        self.assertEqual(result.trigger, "low_confidence")
        self.assertEqual(result.confidence, -0.2)
        self.assertIsNotNone(result.latency_ms)

    async def test_asr_correction_falls_back_when_redecode_has_no_change(self) -> None:
        service = RevisionService()
        context = ContextWindow(session_id="s4", window_size=10)
        segment = Segment(
            id="s4_0",
            text_asr="grain sand",
            confidence=-1.2,
            source_language="ja",
            text_translated="wrong translation",
        )
        context.add_segment(segment)
        nmt = FakeNMTService("corrected translation", completion="great sentence")
        asr = FakeASRService(
            redecode_result=ASRDecodeResult(text="grain sand", confidence=-1.0),
        )

        result = await service.check_asr_correction(
            segment,
            context,
            nmt,
            asr,
            audio_chunk=b"cached-audio",
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(asr.redecode_calls, 1)
        self.assertEqual(nmt.completion_calls, 1)
        self.assertIn("Japanese speech", nmt.last_system_prompt)
        self.assertEqual(result.source_text, "great sentence")
        self.assertEqual(result.correction_source, "llm_post_edit")
        self.assertIsNone(result.confidence)

    async def test_asr_correction_returns_none_when_no_source_change(self) -> None:
        service = RevisionService()
        context = ContextWindow(session_id="s5", window_size=10)
        segment = Segment(
            id="s5_0",
            text_asr="already correct",
            confidence=-1.2,
            text_translated="current translation",
        )
        context.add_segment(segment)
        nmt = FakeNMTService("unused translation", completion="CORRECT")
        asr = FakeASRService(
            redecode_result=ASRDecodeResult(text="already correct", confidence=-0.1),
        )

        result = await service.check_asr_correction(
            segment,
            context,
            nmt,
            asr,
            audio_chunk=b"cached-audio",
        )

        self.assertIsNone(result)
        self.assertEqual(asr.redecode_calls, 1)
        self.assertEqual(nmt.completion_calls, 1)
        self.assertEqual(nmt.translation_calls, 0)


class RevisionLoopGuardTests(unittest.IsolatedAsyncioTestCase):
    """阶段 4：防止过度修正与循环修正。"""

    def _build_context(self) -> tuple[RevisionService, ContextWindow, Segment]:
        service = RevisionService()
        context = ContextWindow(session_id="loop", window_size=10)
        seg_a = Segment(
            id="loop_0",
            text_asr="first sentence",
            confidence=0.95,
            text_translated="first old translation",
        )
        seg_b = Segment(
            id="loop_1",
            text_asr="second sentence",
            confidence=0.95,
            text_translated="second old translation",
        )
        seg_c = Segment(
            id="loop_2",
            text_asr="current",
            confidence=0.95,
            text_translated="current",
        )
        context.add_segment(seg_a)
        context.add_segment(seg_b)
        context.add_segment(seg_c)
        return service, context, seg_c

    async def test_per_segment_max_prevents_oscillation(self) -> None:
        """同一片段修正次数达到上限后不再继续修正（防震荡）。"""
        from core.config import settings

        original_max = settings.revision_max_per_segment
        settings.revision_max_per_segment = 1
        try:
            service, context, trigger = self._build_context()
            nmt = FakeNMTService("completely different translation")

            # 第一次修正：允许
            first = await service.check_and_revise(
                context, nmt, force=True, trigger_segment=trigger, trigger="manual",
            )
            self.assertGreater(len(first), 0)

            # 第二次触发（同一批片段）：片段已修正过 1 次达到上限，全部跳过
            second = await service.check_and_revise(
                context, nmt, force=True, trigger_segment=trigger, trigger="manual",
            )
            self.assertEqual(len(second), 0)

            skipped = service.consume_skipped_counts()
            self.assertGreaterEqual(skipped.get("max_per_segment", 0), 1)
        finally:
            settings.revision_max_per_segment = original_max

    async def test_min_interval_throttles_rapid_revisions(self) -> None:
        """同一片段在最小间隔内不会再次被修正（时间节流）。"""
        from core.config import settings

        original_max = settings.revision_max_per_segment
        original_interval = settings.revision_min_interval_seconds
        settings.revision_max_per_segment = 3
        settings.revision_min_interval_seconds = 3600  # 1 小时，确保触发节流
        try:
            service, context, trigger = self._build_context()
            nmt = FakeNMTService("completely different translation")

            first = await service.check_and_revise(
                context, nmt, force=True, trigger_segment=trigger, trigger="manual",
            )
            self.assertGreater(len(first), 0)

            # 立即再触发：同一片段距上次修正 < 最小间隔，全部跳过
            second = await service.check_and_revise(
                context, nmt, force=True, trigger_segment=trigger, trigger="manual",
            )
            self.assertEqual(len(second), 0)
        finally:
            settings.revision_max_per_segment = original_max
            settings.revision_min_interval_seconds = original_interval

    async def test_asr_correction_respects_per_segment_guard(self) -> None:
        """ASR 纠错同样受片段级修正次数上限约束。"""
        from core.config import settings

        original_max = settings.revision_max_per_segment
        settings.revision_max_per_segment = 1
        try:
            service = RevisionService()
            context = ContextWindow(session_id="asr-loop", window_size=10)
            segment = Segment(
                id="asr-loop_0",
                text_asr="grain sand",
                confidence=-1.2,
                text_translated="wrong translation",
            )
            context.add_segment(segment)
            nmt = FakeNMTService("corrected translation", completion="great sentence")
            asr = FakeASRService()

            first = await service.check_asr_correction(
                segment, context, nmt, asr, audio_chunk=b"cached",
            )
            self.assertIsNotNone(first)

            # 片段已修正 1 次达到上限，第二次直接跳过（不消耗上游调用）
            nmt2 = FakeNMTService("corrected translation", completion="great sentence")
            asr2 = FakeASRService()
            second = await service.check_asr_correction(
                segment, context, nmt2, asr2, audio_chunk=b"cached",
            )
            self.assertIsNone(second)
            self.assertEqual(asr2.redecode_calls, 0)
            self.assertEqual(nmt2.completion_calls, 0)
        finally:
            settings.revision_max_per_segment = original_max

    async def test_total_revision_cap(self) -> None:
        """会话总修正次数达到上限后停止一切修正（防 API 成本失控）。"""
        from core.config import settings

        original_total = settings.revision_max_total
        settings.revision_max_total = 1
        try:
            service, context, trigger = self._build_context()
            nmt = FakeNMTService("completely different translation")

            first = await service.check_and_revise(
                context, nmt, force=True, trigger_segment=trigger, trigger="manual",
            )
            self.assertGreater(len(first), 0)

            second = await service.check_and_revise(
                context, nmt, force=True, trigger_segment=trigger, trigger="manual",
            )
            self.assertEqual(len(second), 0)

            skipped = service.consume_skipped_counts()
            self.assertGreaterEqual(skipped.get("max_total", 0), 1)
        finally:
            settings.revision_max_total = original_total


if __name__ == "__main__":
    unittest.main()
