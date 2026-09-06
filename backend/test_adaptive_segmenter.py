"""Unit tests for the adaptive voice-activity segmenter."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np


BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.adaptive_segmenter import AdaptiveSegmenter


class FakeVAD:
    """可控的语音活动检测，用于测试切分规则。"""

    def __init__(self, speech_chunks: set[int]) -> None:
        self._speech_chunks = speech_chunks
        self.reset_calls = 0

    def is_speech(self, samples: np.ndarray) -> bool:
        # 用采样长度索引模拟"某段是语音"：长度在集合中的视为语音帧
        return samples.size in self._speech_chunks

    def reset(self) -> None:
        self.reset_calls += 1


def make_samples(size: int, value: float = 0.1) -> np.ndarray:
    return np.full(size, value, dtype=np.float32)


class AdaptiveSegmenterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sample_rate = 16000
        # min 800ms / max 8000ms / silence 400ms
        self.min_samples = int(self.sample_rate * 0.8)
        self.max_samples = int(self.sample_rate * 8.0)
        self.silence_samples = int(self.sample_rate * 0.4)

    def test_does_not_emit_below_min_duration(self) -> None:
        segmenter = AdaptiveSegmenter(
            sample_rate=self.sample_rate,
            min_segment_ms=800,
            max_segment_ms=8000,
            silence_boundary_ms=400,
        )
        # 累积 500ms，低于 min
        for _ in range(5):
            self.assertFalse(segmenter.should_emit(make_samples(1600)))
        self.assertEqual(segmenter.take_buffer().size, 1600 * 5)

    def test_emits_on_max_duration_even_without_silence(self) -> None:
        segmenter = AdaptiveSegmenter(
            sample_rate=self.sample_rate,
            min_segment_ms=800,
            max_segment_ms=8000,
            silence_boundary_ms=400,
        )
        # 累积 8 秒语音帧（模拟连续讲话无停顿）
        emitted = False
        for _ in range(80):
            if segmenter.should_emit(make_samples(1600)):
                emitted = True
                break
        self.assertTrue(emitted)
        self.assertEqual(segmenter.take_buffer().size, 1600 * 80)

    def test_emits_after_silence_boundary_when_vad_detects_silence(self) -> None:
        vad = FakeVAD(speech_chunks={1600})
        segmenter = AdaptiveSegmenter(
            sample_rate=self.sample_rate,
            min_segment_ms=800,
            max_segment_ms=8000,
            silence_boundary_ms=400,
            vad=vad,
        )
        # 先送语音帧（size 1600），够 min
        for _ in range(10):
            self.assertFalse(segmenter.should_emit(make_samples(1600)))

        # 再送静音帧（size 3200，不在 speech_chunks），累积 3200*5 = 1 秒 > 400ms
        emitted = False
        for _ in range(5):
            if segmenter.should_emit(make_samples(3200)):
                emitted = True
                break
        self.assertTrue(emitted)

    def test_vad_speech_resets_silence_counter(self) -> None:
        vad = FakeVAD(speech_chunks={1600})
        segmenter = AdaptiveSegmenter(
            sample_rate=self.sample_rate,
            min_segment_ms=800,
            max_segment_ms=8000,
            silence_boundary_ms=400,
            vad=vad,
        )
        # 送语音帧到超 min
        for _ in range(10):
            segmenter.should_emit(make_samples(1600))

        # 静音帧中断后马上回到语音帧：静音计数被重置，不触发。
        # 注意静音帧仍计入累积 buffer（只是不触发切分）。
        segmenter.should_emit(make_samples(3200))
        segmenter.should_emit(make_samples(1600))
        self.assertEqual(segmenter.take_buffer().size, 1600 * 10 + 3200 + 1600)

    def test_prepend_restores_audio_after_failed_decode(self) -> None:
        segmenter = AdaptiveSegmenter(
            sample_rate=self.sample_rate,
            min_segment_ms=800,
            max_segment_ms=8000,
            silence_boundary_ms=400,
        )
        segmenter.should_emit(make_samples(1600))
        segmenter.should_emit(make_samples(1600))
        audio = segmenter.take_buffer()
        self.assertEqual(audio.size, 3200)

        # 模拟解码失败：放回
        segmenter.prepend(audio)
        self.assertEqual(segmenter.take_buffer().size, 3200)

    def test_reset_clears_buffer_and_vad(self) -> None:
        vad = FakeVAD(speech_chunks={1600})
        segmenter = AdaptiveSegmenter(
            sample_rate=self.sample_rate,
            min_segment_ms=800,
            max_segment_ms=8000,
            silence_boundary_ms=400,
            vad=vad,
        )
        segmenter.should_emit(make_samples(1600))
        segmenter.reset()
        self.assertEqual(segmenter.take_buffer().size, 0)
        self.assertGreaterEqual(vad.reset_calls, 1)

    def test_empty_samples_never_emit(self) -> None:
        segmenter = AdaptiveSegmenter(
            sample_rate=self.sample_rate,
            min_segment_ms=800,
            max_segment_ms=8000,
            silence_boundary_ms=400,
        )
        self.assertFalse(segmenter.should_emit(np.empty(0, dtype=np.float32)))

    def test_vad_parameters_drive_cut_points(self) -> None:
        """V2.4：vad_min_speech_ms / vad_min_silence_ms / vad_max_sentence_s 参数化切分。

        用 250ms 最小语音 + 500ms 静音边界 + 2s 最大句长验证：
        - 未达 min_speech 不切分；
        - 静音达 min_silence 即切分；
        - 超 max_sentence 强制切分。
        """
        min_speech = int(self.sample_rate * 0.25)

        segmenter = AdaptiveSegmenter(
            sample_rate=self.sample_rate,
            min_segment_ms=250,
            max_segment_ms=2000,
            silence_boundary_ms=500,
        )

        # 累积 200ms < 250ms，不切分
        self.assertFalse(segmenter.should_emit(make_samples(min_speech - 100)))
        self.assertEqual(segmenter.take_buffer().size, min_speech - 100)

        # 纯时长路径：超过 max_sentence 强制切分
        segmenter2 = AdaptiveSegmenter(
            sample_rate=self.sample_rate,
            min_segment_ms=250,
            max_segment_ms=2000,
            silence_boundary_ms=500,
        )
        emitted = False
        for _ in range(30):  # 30 * 100ms = 3s > 2s
            if segmenter2.should_emit(make_samples(1600)):
                emitted = True
                break
        self.assertTrue(emitted)
        # 达到 max_sentence (2s=32000) 即强制切分：20 帧 * 1600 = 32000
        self.assertEqual(segmenter2.take_buffer().size, 20 * 1600)

        # VAD 静音边界：250ms 语音帧 + 500ms 静音帧触发
        vad = FakeVAD(speech_chunks={min_speech})
        segmenter3 = AdaptiveSegmenter(
            sample_rate=self.sample_rate,
            min_segment_ms=250,
            max_segment_ms=2000,
            silence_boundary_ms=500,
            vad=vad,
        )
        segmenter3.should_emit(make_samples(min_speech))  # 语音帧，够 min
        emitted = False
        for _ in range(6):  # 6 * 100ms = 600ms 静音 > 500ms
            if segmenter3.should_emit(make_samples(1600)):
                emitted = True
                break
        self.assertTrue(emitted)


if __name__ == "__main__":
    unittest.main()
