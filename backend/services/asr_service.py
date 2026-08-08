"""Streaming ASR service backed by remote OpenAI-compatible ASR or Whisper."""

from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional
import wave

import numpy as np
from loguru import logger

from core.config import settings
from core.exceptions import ASRError
from services.adaptive_segmenter import (
    AdaptiveSegmenter,
    SileroVoiceActivityDetector,
    create_silero_vad,
)
from services.language_config import normalize_source_language, whisper_language_code


FinalCallback = Callable[[str, float], Awaitable[None]]
PartialCallback = Callable[[str], Awaitable[None]]


@dataclass(frozen=True)
class ASRDecodeResult:
    text: str
    confidence: float


class ASRService:
    def __init__(self) -> None:
        self._engine = settings.asr_engine
        self._model = None
        self._client = None
        self._on_partial: Optional[PartialCallback] = None
        self._on_final: Optional[FinalCallback] = None
        self._audio_buffer: list[np.ndarray] = []
        self._sample_rate = settings.audio_sample_rate
        self._vad_enabled = True
        self._latest_input_audio_chunk = b""
        self._last_segment_audio_chunk = b""
        self._source_language = normalize_source_language(settings.source_language)
        self._vad: Optional[SileroVoiceActivityDetector] = None
        self._segmenter: Optional[AdaptiveSegmenter] = None

    def set_on_partial(self, callback: PartialCallback) -> None:
        self._on_partial = callback

    def set_on_final(self, callback: FinalCallback) -> None:
        self._on_final = callback

    def set_language(self, source_language: str) -> None:
        self._source_language = normalize_source_language(source_language)

    async def initialize(self) -> None:
        # 惰性加载 VAD：失败则降级为纯时长切分，不影响主链路
        if settings.adaptive_segmenter_enabled:
            self._vad = create_silero_vad(sample_rate=self._sample_rate)
        self._segmenter = self._build_segmenter()

        if self._engine == "whisper":
            await self._init_whisper()
            return
        if self._engine in {"openai", "remote"}:
            await self._init_openai()
            return
        if self._engine == "deepgram":
            logger.info("Deepgram ASR engine selected (not implemented)")
            return
        if self._engine == "azure":
            logger.info("Azure ASR engine selected (not implemented)")
            return
        raise ASRError(f"Unknown ASR engine: {self._engine}")

    def _build_segmenter(self) -> Optional[AdaptiveSegmenter]:
        """按配置构造分段器；禁用或构造失败时返回 None（退回固定窗口）。"""
        if not settings.adaptive_segmenter_enabled:
            return None
        return AdaptiveSegmenter(
            sample_rate=self._sample_rate,
            min_segment_ms=settings.segment_min_ms,
            max_segment_ms=settings.segment_max_ms,
            silence_boundary_ms=settings.segment_silence_boundary_ms,
            vad=self._vad,
        )

    async def _init_whisper(self) -> None:
        try:
            from faster_whisper import WhisperModel

            logger.info(
                "Loading Whisper model {} on {}",
                settings.whisper_model,
                settings.whisper_device,
            )
            self._model = WhisperModel(
                settings.whisper_model,
                device=settings.whisper_device,
                compute_type=settings.whisper_compute_type,
            )
            logger.info("Whisper model loaded successfully")
        except Exception as exc:
            logger.error("Failed to load Whisper model: {}", exc)
            raise ASRError(f"Whisper initialization failed: {exc}")

    async def _init_openai(self) -> None:
        try:
            from openai import AsyncOpenAI

            api_key = settings.asr_openai_api_key or settings.openai_api_key
            base_url = settings.asr_openai_base_url or settings.openai_base_url
            self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
            logger.info(
                "OpenAI-compatible ASR client initialized with model {}",
                settings.asr_openai_model,
            )
        except Exception as exc:
            logger.error("Failed to init OpenAI-compatible ASR client: {}", exc)
            raise ASRError(f"OpenAI-compatible ASR init failed: {exc}")

    async def process_chunk(self, audio_bytes: bytes) -> int:
        if self._engine == "whisper":
            return await self._process_whisper(audio_bytes)
        if self._engine in {"openai", "remote"}:
            return await self._process_openai(audio_bytes)
        return 0

    async def _process_openai(self, audio_bytes: bytes) -> int:
        audio_array = np.frombuffer(audio_bytes, dtype=np.float32)
        self._latest_input_audio_chunk = audio_bytes

        if self._segmenter is not None:
            if self._segmenter.should_emit(audio_array):
                return await self._trigger_openai_decode()
            return 0

        # 回退路径：固定 2 秒窗口（segmenter 不可用时）
        self._audio_buffer.append(audio_array)
        total_samples = sum(len(chunk) for chunk in self._audio_buffer)
        min_samples = self._sample_rate * 2
        if total_samples >= min_samples:
            return await self._trigger_openai_decode()
        return 0

    async def _trigger_openai_decode(self) -> int:
        if not self._client:
            return 0

        audio = self._take_audio_buffer()
        if audio.size == 0:
            return 0
        self._last_segment_audio_chunk = audio.astype(np.float32, copy=False).tobytes()

        try:
            result = await self._transcribe_openai_float32(audio)
            if result and result.text and self._on_final:
                await self._on_final(result.text, result.confidence)
                return 1
            return 0
        except Exception as exc:
            logger.error("OpenAI-compatible ASR decode error: {}", exc)
            self._restore_audio_buffer(audio)
            return 0

    async def _process_whisper(self, audio_bytes: bytes) -> int:
        audio_array = np.frombuffer(audio_bytes, dtype=np.float32)
        self._latest_input_audio_chunk = audio_bytes

        if self._segmenter is not None:
            if self._segmenter.should_emit(audio_array):
                return await self._trigger_whisper_decode()
            return 0

        # 回退路径：固定 2 秒窗口（segmenter 不可用时）
        self._audio_buffer.append(audio_array)
        total_samples = sum(len(chunk) for chunk in self._audio_buffer)
        min_samples = self._sample_rate * 2
        if total_samples >= min_samples:
            return await self._trigger_whisper_decode()
        return 0

    async def _trigger_whisper_decode(self) -> int:
        if not self._model:
            return 0

        audio = self._take_audio_buffer()
        if audio.size == 0:
            return 0
        self._last_segment_audio_chunk = audio.astype(np.float32, copy=False).tobytes()

        try:
            results = await self._transcribe_float32(audio)

            emitted = 0
            for result in results:
                if result.text and self._on_final:
                    await self._on_final(result.text, result.confidence)
                    emitted += 1
            return emitted
        except Exception as exc:
            logger.error("Whisper decode error: {}", exc)
            self._restore_audio_buffer(audio)
            return 0

    def _take_audio_buffer(self) -> np.ndarray:
        """从分段器或回退缓冲取出累积音频。"""
        if self._segmenter is not None:
            return self._segmenter.take_buffer()
        if not self._audio_buffer:
            return np.empty(0, dtype=np.float32)
        audio = np.concatenate(self._audio_buffer)
        self._audio_buffer = []
        return audio

    def _restore_audio_buffer(self, audio: np.ndarray) -> None:
        """解码失败时把音频放回缓冲头部，避免丢数据。"""
        if self._segmenter is not None:
            self._segmenter.prepend(audio)
        else:
            self._audio_buffer.insert(0, audio)

    async def redecode_audio(self, audio_bytes: bytes) -> ASRDecodeResult | None:
        """Re-run the active ASR backend on cached segment audio for correction."""
        if not audio_bytes:
            return None

        audio = np.frombuffer(audio_bytes, dtype=np.float32)
        if audio.size == 0:
            return None

        if self._engine in {"openai", "remote"} and self._client:
            try:
                return await self._transcribe_openai_float32(audio)
            except Exception as exc:
                logger.warning("OpenAI-compatible ASR re-decode failed: {}", exc)
                return None

        if self._engine != "whisper" or not self._model:
            return None

        try:
            results = await self._transcribe_float32(audio)
        except Exception as exc:
            logger.warning("Whisper re-decode failed: {}", exc)
            return None

        if not results:
            return None

        text = " ".join(result.text for result in results if result.text).strip()
        if not text:
            return None

        confidence = sum(result.confidence for result in results) / len(results)
        return ASRDecodeResult(text=text, confidence=confidence)

    async def _transcribe_openai_float32(self, audio: np.ndarray) -> ASRDecodeResult | None:
        if not self._client:
            return None

        wav_bytes = float32_audio_to_wav_bytes(audio, self._sample_rate)
        language = whisper_language_code(self._source_language)
        request = {
            "model": settings.asr_openai_model,
            "file": ("audio.wav", wav_bytes, "audio/wav"),
            "response_format": "json",
        }
        if language:
            request["language"] = language

        response = await self._client.audio.transcriptions.create(**request)
        text = extract_transcription_text(response)
        if not text:
            return None
        return ASRDecodeResult(text=text, confidence=0.0)

    async def _transcribe_float32(self, audio: np.ndarray) -> list[ASRDecodeResult]:
        segments, _info = await asyncio.to_thread(
            self._model.transcribe,
            audio,
            beam_size=5,
            language=whisper_language_code(self._source_language),
            vad_filter=self._vad_enabled,
            without_timestamps=True,
        )

        results: list[ASRDecodeResult] = []
        for segment in segments:
            text = segment.text.strip()
            if text:
                results.append(ASRDecodeResult(
                    text=text,
                    confidence=segment.avg_logprob,
                ))
        return results

    def get_last_audio_chunk(self) -> bytes:
        return self._last_segment_audio_chunk or self._latest_input_audio_chunk

    def create_session(self) -> ASRService:
        """Create isolated stream state that shares the initialized model."""
        service = ASRService()
        service._model = self._model
        service._client = self._client
        service._source_language = self._source_language
        service._vad = self._vad
        service._segmenter = service._build_segmenter()
        return service

    def reset_session_state(self) -> None:
        self._on_partial = None
        self._on_final = None
        self._audio_buffer.clear()
        self._latest_input_audio_chunk = b""
        self._last_segment_audio_chunk = b""
        if self._segmenter is not None:
            self._segmenter.reset()

    async def shutdown(self) -> None:
        if self._model:
            del self._model
            self._model = None
        self._client = None
        self._audio_buffer.clear()
        self._latest_input_audio_chunk = b""
        self._last_segment_audio_chunk = b""
        if self._segmenter is not None:
            self._segmenter.reset()
        self._vad = None
        logger.info("ASR service shut down")


def float32_audio_to_wav_bytes(audio: np.ndarray, sample_rate: int) -> bytes:
    clipped = np.clip(audio, -1.0, 1.0)
    pcm16 = (clipped * 32767).astype("<i2", copy=False)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm16.tobytes())
    return buffer.getvalue()


def extract_transcription_text(response: object) -> str:
    if isinstance(response, dict):
        value = response.get("text")
        return value.strip() if isinstance(value, str) else ""

    value = getattr(response, "text", "")
    return value.strip() if isinstance(value, str) else ""
