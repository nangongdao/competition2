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


if __name__ == "__main__":
    unittest.main()
