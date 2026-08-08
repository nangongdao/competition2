"""基于嵌入聚类的轻量说话人分离。

多人会议场景下，不区分说话人的字幕可读性极差。本服务为每个 segment
标注说话人 ID（speaker_1、speaker_2 ...），前端据此着色显示。

生产环境可将 ``SpectralEmbeddingExtractor`` 替换为 pyannote.audio 等
预训练说话人嵌入模型；默认的谱特征提取器零依赖、可离线运行。
"""

from __future__ import annotations

from typing import Protocol

import numpy as np


class VoiceEmbeddingExtractor(Protocol):
    """说话人嵌入提取器接口。"""

    def extract(self, samples: np.ndarray) -> np.ndarray:
        """从 float32 音频采样中提取说话人嵌入向量。"""
        ...


class SpectralEmbeddingExtractor:
    """零依赖的谱特征嵌入（log-mel 均值）。

    计算 log-mel 频谱的帧均值作为说话人特征。相比真实声纹模型精度有限，
    但零依赖、可离线，足以支撑多人场景的粗略区分（不同说话人音色的
    log-mel 能量分布差异明显）。
    """

    FRAME_LEN = 400  # 25ms @ 16kHz
    HOP = 160        # 10ms @ 16kHz
    N_MELS = 20

    def __init__(self, *, sample_rate: int = 16000) -> None:
        self._sample_rate = sample_rate
        self._filterbank = _mel_filterbank(self.N_MELS, self.FRAME_LEN, sample_rate)

    def extract(self, samples: np.ndarray) -> np.ndarray:
        if samples.size == 0:
            return np.zeros(self.N_MELS, dtype=np.float32)

        audio = samples / (np.abs(samples).max() + 1e-8)
        frames = _frame_audio(audio, self.FRAME_LEN, self.HOP)
        if frames.shape[0] == 0:
            return np.zeros(self.N_MELS, dtype=np.float32)

        window = np.hanning(self.FRAME_LEN)
        spectra = np.abs(np.fft.rfft(frames * window, axis=1))
        mel_energies = np.log(self._filterbank @ spectra.T + 1e-10)  # (n_mels, n_frames)
        embedding = mel_energies.mean(axis=1).astype(np.float32)

        norm = np.linalg.norm(embedding)
        if norm < 1e-8:
            return np.zeros(self.N_MELS, dtype=np.float32)
        return embedding / norm


class DiarizationService:
    """基于在线聚类（质心 + 余弦相似度）的说话人分离。

    每个新片段提取嵌入后与已知说话人质心比较：
    - 超过相似度阈值 → 归入最相似说话人，并用 EMA 在线更新质心；
    - 否则创建新说话人。
    """

    def __init__(
        self,
        *,
        extractor: VoiceEmbeddingExtractor | None = None,
        similarity_threshold: float = 0.85,
    ) -> None:
        self._extractor = extractor or SpectralEmbeddingExtractor()
        self._threshold = similarity_threshold
        self._centroids: dict[str, np.ndarray] = {}
        self._next_speaker_index = 1

    def identify(self, samples: np.ndarray) -> str:
        """识别音频片段的说话人。

        Args:
            samples: float32 单声道采样数据。

        Returns:
            说话人标识，如 "speaker_1"。
        """
        embedding = self._extractor.extract(samples)

        best_id: str | None = None
        best_score = -1.0
        for speaker_id, centroid in self._centroids.items():
            score = float(np.dot(embedding, centroid))
            if score > best_score:
                best_id = speaker_id
                best_score = score

        if best_id is None or best_score < self._threshold:
            new_id = f"speaker_{self._next_speaker_index}"
            self._next_speaker_index += 1
            self._centroids[new_id] = embedding
            return new_id

        # 在线更新中心（指数移动平均），让质心随说话人漂移
        centroid = self._centroids[best_id]
        updated = 0.9 * centroid + 0.1 * embedding
        norm = np.linalg.norm(updated)
        self._centroids[best_id] = updated / (norm + 1e-8) if norm > 0 else centroid
        return best_id

    def reset(self) -> None:
        """清空说话人质心（新会话开始时调用）。"""
        self._centroids = {}
        self._next_speaker_index = 1


def _frame_audio(audio: np.ndarray, frame_len: int, hop: int) -> np.ndarray:
    """把采样切成重叠帧，不足一帧的部分丢弃。"""
    if audio.size < frame_len:
        return np.empty((0, frame_len), dtype=audio.dtype)
    count = 1 + (audio.size - frame_len) // hop
    indices = (
        np.arange(frame_len)[None, :]
        + hop * np.arange(count)[:, None]
    )
    return audio[indices]


def _mel_filterbank(n_mels: int, frame_len: int, sample_rate: int) -> np.ndarray:
    """构造三角 mel 滤波器组（(n_mels, n_bins)）。"""
    n_bins = frame_len // 2 + 1
    hz_points = _hz_to_mel(np.linspace(_mel_to_hz(0.0), _mel_to_hz(sample_rate / 2), n_mels + 2))
    bin_points = np.floor((frame_len + 1) * hz_points / sample_rate).astype(int)
    bin_points = np.clip(bin_points, 0, n_bins - 1)

    filterbank = np.zeros((n_mels, n_bins), dtype=np.float64)
    for mel_index in range(n_mels):
        left, center, right = (
            bin_points[mel_index],
            bin_points[mel_index + 1],
            bin_points[mel_index + 2],
        )
        if center > left:
            filterbank[mel_index, left:center] = (
                np.arange(left, center) - left
            ) / (center - left)
        if right > center:
            filterbank[mel_index, center:right] = (
                right - np.arange(center, right)
            ) / (right - center)
    return filterbank


def _hz_to_mel(hz: float) -> float:
    return 2595.0 * np.log10(1.0 + hz / 700.0)


def _mel_to_hz(mel: float) -> float:
    return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)
