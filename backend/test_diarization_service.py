"""Unit tests for the speaker diarization service."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np


BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.diarization_service import DiarizationService, SpectralEmbeddingExtractor


def make_tone(frequency: float, seconds: float = 0.5) -> np.ndarray:
    sample_rate = 16000
    samples = np.arange(round(seconds * sample_rate))
    return (0.3 * np.sin(2 * np.pi * frequency * samples / sample_rate)).astype(np.float32)


class FixedEmbeddingExtractor:
    """返回预设嵌入的提取器，用于隔离测试聚类逻辑。"""

    def __init__(self, embeddings: list[np.ndarray]) -> None:
        self._embeddings = embeddings
        self._call_index = 0

    def extract(self, _samples: np.ndarray) -> np.ndarray:
        embedding = self._embeddings[self._call_index % len(self._embeddings)]
        self._call_index += 1
        return embedding


def unit_vector(index: int, dimension: int = 16) -> np.ndarray:
    vector = np.zeros(dimension, dtype=np.float32)
    vector[index] = 1.0
    return vector


class SpectralEmbeddingExtractorTests(unittest.TestCase):
    def test_extract_is_deterministic(self) -> None:
        extractor = SpectralEmbeddingExtractor()

        first = extractor.extract(make_tone(220.0))
        second = extractor.extract(make_tone(220.0))

        np.testing.assert_allclose(first, second)

    def test_extract_returns_unit_norm_embedding(self) -> None:
        extractor = SpectralEmbeddingExtractor()
        embedding = extractor.extract(make_tone(440.0))
        self.assertAlmostEqual(float(np.linalg.norm(embedding)), 1.0, places=5)

    def test_extract_empty_samples_returns_zero_vector(self) -> None:
        extractor = SpectralEmbeddingExtractor()
        embedding = extractor.extract(np.empty(0, dtype=np.float32))
        self.assertEqual(embedding.shape[0], 20)
        self.assertEqual(float(np.sum(np.abs(embedding))), 0.0)


class DiarizationServiceTests(unittest.TestCase):
    def test_assigns_same_speaker_for_similar_audio(self) -> None:
        service = DiarizationService(
            extractor=FixedEmbeddingExtractor([unit_vector(0), unit_vector(0)]),
            similarity_threshold=0.90,
        )

        first = service.identify(np.empty(4, dtype=np.float32))
        second = service.identify(np.empty(4, dtype=np.float32))

        self.assertEqual(first, second)
        self.assertTrue(first.startswith("speaker_"))

    def test_assigns_distinct_speakers_for_different_audio(self) -> None:
        service = DiarizationService(
            extractor=FixedEmbeddingExtractor([
                unit_vector(0),
                unit_vector(1),
                unit_vector(2),
            ]),
            similarity_threshold=0.90,
        )

        first = service.identify(np.empty(4, dtype=np.float32))
        second = service.identify(np.empty(4, dtype=np.float32))
        third = service.identify(np.empty(4, dtype=np.float32))

        self.assertEqual(len({first, second, third}), 3)

    def test_reassigns_back_to_known_speaker(self) -> None:
        service = DiarizationService(
            extractor=FixedEmbeddingExtractor([
                unit_vector(0),
                unit_vector(1),
                unit_vector(0),
            ]),
            similarity_threshold=0.90,
        )

        speaker_a = service.identify(np.empty(4, dtype=np.float32))
        service.identify(np.empty(4, dtype=np.float32))
        again = service.identify(np.empty(4, dtype=np.float32))

        self.assertEqual(again, speaker_a)

    def test_reset_clears_speakers(self) -> None:
        service = DiarizationService(
            extractor=FixedEmbeddingExtractor([unit_vector(0)]),
            similarity_threshold=0.90,
        )

        first = service.identify(np.empty(4, dtype=np.float32))
        service.reset()
        after_reset = service.identify(np.empty(4, dtype=np.float32))

        self.assertEqual(first, "speaker_1")
        self.assertEqual(after_reset, "speaker_1")


if __name__ == "__main__":
    unittest.main()
