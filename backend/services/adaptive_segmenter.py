"""自适应语音分段器。

结合 VAD 静音检测与最大/最小时长约束，在自然停顿处切分语音，
避免把完整句子从中间截断导致翻译质量下降（原固定 2 秒窗口的问题）。
"""

from __future__ import annotations

from typing import Protocol

import numpy as np
from loguru import logger

from core.config import settings


class VoiceActivityDetector(Protocol):
    """语音活动检测接口。"""

    def is_speech(self, samples: np.ndarray) -> bool:
        """判断一段采样是否包含语音。"""
        ...

    def reset(self) -> None:
        """重置流式状态（新会话开始时调用）。"""
        ...


class SileroVoiceActivityDetector:
    """基于 Silero VAD 模型的语音活动检测。

    将输入采样拆分为 512 采样帧（16kHz 下约 32ms），逐帧计算语音概率，
    取多数表决作为整个片段的判定。
    """

    FRAME_SAMPLES = 512

    def __init__(
        self,
        model: object,
        *,
        sample_rate: int = 16000,
        threshold: float = 0.5,
    ) -> None:
        self._model = model
        self._sample_rate = sample_rate
        self._threshold = threshold

    def is_speech(self, samples: np.ndarray) -> bool:
        if samples.size == 0:
            return False

        # 每次调用前重置流式状态，使推理独立于会话——
        # VAD 模型实例被多会话共享，非流式独立推理避免跨会话状态污染。
        self.reset()

        count = samples.size // self.FRAME_SAMPLES
        if count == 0:
            padded = np.concatenate([
                samples,
                np.zeros(self.FRAME_SAMPLES - samples.size, dtype=np.float32),
            ])
            return self._frame_probability(padded) >= self._threshold

        frames = samples[: count * self.FRAME_SAMPLES].reshape(count, self.FRAME_SAMPLES)
        speech_frames = sum(
            1 for frame in frames if self._frame_probability(frame) >= self._threshold
        )
        return speech_frames / count >= 0.5

    def reset(self) -> None:
        reset_states = getattr(self._model, "reset_states", None)
        if callable(reset_states):
            reset_states()

    def _frame_probability(self, frame: np.ndarray) -> float:
        """对单个 512 采样帧计算语音概率。"""
        try:
            import torch

            tensor = torch.from_numpy(frame).reshape(1, -1)
            # no_grad：Silero 模型参数 requires_grad，推理时不构造计算图，
            # 避免 ".item() converting tensor with requires_grad" 告警与额外开销。
            with torch.no_grad():
                probability = self._model(tensor, self._sample_rate)
            return float(probability)
        except Exception as exc:
            logger.warning("Silero VAD frame inference failed: {}", exc)
            return 0.0


def create_silero_vad(
    *,
    sample_rate: int = settings.audio_sample_rate,
    threshold: float = settings.vad_threshold,
) -> SileroVoiceActivityDetector | None:
    """懒加载 Silero VAD 模型。

    VAD 模型首次加载会下载权重，可能失败（离线/无网络）。失败时返回 None，
    调用方降级为纯时长切分，不影响主链路。
    """
    try:
        from silero_vad import load_silero_vad

        model = load_silero_vad()
        return SileroVoiceActivityDetector(model, sample_rate=sample_rate, threshold=threshold)
    except Exception as exc:
        logger.warning("Silero VAD unavailable, falling back to duration-only segmentation: {}", exc)
        return None


class AdaptiveSegmenter:
    """自适应语音分段器。

    切分规则：
    - 累积时长 < ``min_segment_ms``：不切分（避免碎片化）；
    - 累积时长 >= ``max_segment_ms``：强制切分（防止延迟过高）；
    - 介于两者之间：当检测到连续静音达到 ``silence_boundary_ms`` 时切分
      （在自然停顿处切分，不截断句子）。
    """

    def __init__(
        self,
        *,
        sample_rate: int = 16000,
        min_segment_ms: int = 800,
        max_segment_ms: int = 8000,
        silence_boundary_ms: int = 400,
        vad: VoiceActivityDetector | None = None,
    ) -> None:
        self._min_samples = int(sample_rate * min_segment_ms / 1000)
        self._max_samples = int(sample_rate * max_segment_ms / 1000)
        self._silence_boundary_samples = int(sample_rate * silence_boundary_ms / 1000)
        self._vad = vad
        self._buffer: list[np.ndarray] = []
        self._buffer_samples = 0
        self._silence_samples = 0

    def should_emit(self, samples: np.ndarray) -> bool:
        """累积音频并判断是否应触发解码切分。

        Args:
            samples: 本帧的 float32 采样数据。

        Returns:
            True 时应调用 ``take_buffer`` 取走累积音频并解码。
        """
        if samples.size == 0:
            return False

        self._buffer.append(samples)
        self._buffer_samples += samples.size

        if self._buffer_samples >= self._max_samples:
            return True
        if self._buffer_samples < self._min_samples:
            return False
        if self._vad is not None:
            if self._vad.is_speech(samples):
                self._silence_samples = 0
            else:
                self._silence_samples += samples.size
            if self._silence_samples >= self._silence_boundary_samples:
                return True
        return False

    def take_buffer(self) -> np.ndarray:
        """取出累积音频并清空内部状态。"""
        if not self._buffer:
            self._buffer_samples = 0
            self._silence_samples = 0
            return np.empty(0, dtype=np.float32)

        audio = np.concatenate(self._buffer)
        self._buffer = []
        self._buffer_samples = 0
        self._silence_samples = 0
        return audio

    def prepend(self, samples: np.ndarray) -> None:
        """将解码失败的音频放回缓冲头部（失败重试不丢数据）。"""
        if samples.size == 0:
            return
        self._buffer.insert(0, samples)
        self._buffer_samples += samples.size

    def reset(self) -> None:
        """清空缓冲并重置 VAD 流式状态。"""
        self._buffer = []
        self._buffer_samples = 0
        self._silence_samples = 0
        if self._vad is not None:
            self._vad.reset()
