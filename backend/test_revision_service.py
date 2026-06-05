import unittest
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from models.segment import ContextWindow, Segment
from services.revision_service import RevisionService


class FakeNMTService:
    def __init__(self, translation: str, completion: str = "CORRECT") -> None:
        self.translation = translation
        self.completion = completion

    async def translate_stream(self, _context: ContextWindow, _segment: Segment):
        yield self.translation
        yield "<FINAL>"

    async def complete_text(self, _prompt: str, *, system_prompt: str) -> str:
        assert "ASR post-editor" in system_prompt
        return self.completion


class FakeASRService:
    def __init__(self, payload: bytes = b"audio") -> None:
        self.payload = payload

    def get_last_audio_chunk(self) -> bytes:
        return self.payload


class RevisionServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_translation_revision_returns_translation_correction(self) -> None:
        service = RevisionService()
        context = ContextWindow(session_id="s1", window_size=10)
        context.add_segment(Segment(id="s1_0", text_asr="hello", confidence=0.95, text_translated="你好"))
        context.add_segment(Segment(id="s1_1", text_asr="world", confidence=0.95, text_translated="世界"))
        context.add_segment(Segment(id="s1_2", text_asr="today", confidence=0.95, text_translated="今天"))

        results = await service.check_and_revise(
            context,
            FakeNMTService("完全不同的翻译"),
            force=True,
            trigger_segment=context.get_all()[-1],
        )

        self.assertEqual(len(results), 2)
        self.assertTrue(all(item.reason == "translation_correction" for item in results))
        self.assertTrue(all(item.source_text is None for item in results))

    async def test_asr_correction_returns_source_and_translation(self) -> None:
        service = RevisionService()
        context = ContextWindow(session_id="s2", window_size=10)
        context.add_segment(Segment(id="s2_0", text_asr="previous sentence", confidence=0.95, text_translated="前一句"))
        segment = Segment(
            id="s2_1",
            text_asr="grain sand",
            confidence=-1.2,
            text_translated="错误翻译",
        )
        context.add_segment(segment)

        result = await service.check_asr_correction(
            segment,
            context,
            FakeNMTService("修正后的译文", completion="great sentence"),
            FakeASRService(),
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.reason, "asr_correction")
        self.assertEqual(result.source_text, "great sentence")
        self.assertEqual(result.new_text, "修正后的译文")


if __name__ == "__main__":
    unittest.main()
