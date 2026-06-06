"""Streaming ASR service backed by Faster-Whisper."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

import numpy as np
from loguru import logger

from core.config import settings
from core.exceptions import ASRError


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
        self._on_partial: Optional[PartialCallback] = None
        self._on_final: Optional[FinalCallback] = None
        self._audio_buffer: list[np.ndarray] = []
        self._sample_rate = settings.audio_sample_rate
        self._vad_enabled = True
        self._latest_input_audio_chunk = b""
        self._last_segment_audio_chunk = b""

    def set_on_partial(self, callback: PartialCallback) -> None:
        self._on_partial = callback

    def set_on_final(self, callback: FinalCallback) -> None:
        self._on_final = callback

    async def initialize(self) -> None:
        if self._engine == "whisper":
            await self._init_whisper()
            return
        if self._engine == "deepgram":
            logger.info("Deepgram ASR engine selected (not implemented)")
            return
        if self._engine == "azure":
            logger.info("Azure ASR engine selected (not implemented)")
            return
        raise ASRError(f"Unknown ASR engine: {self._engine}")

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

    async def process_chunk(self, audio_bytes: bytes) -> None:
        if self._engine != "whisper":
            return
        await self._process_whisper(audio_bytes)

    async def _process_whisper(self, audio_bytes: bytes) -> None:
        audio_array = np.frombuffer(audio_bytes, dtype=np.float32)
        self._latest_input_audio_chunk = audio_bytes
        self._audio_buffer.append(audio_array)

        total_samples = sum(len(chunk) for chunk in self._audio_buffer)
        min_samples = self._sample_rate * 2
        if total_samples >= min_samples:
            await self._trigger_whisper_decode()

    async def _trigger_whisper_decode(self) -> None:
        if not self._model or not self._audio_buffer:
            return

        audio_buffer_snapshot = self._audio_buffer
        self._audio_buffer = []
        audio = np.concatenate(audio_buffer_snapshot)
        self._last_segment_audio_chunk = audio.astype(np.float32, copy=False).tobytes()

        try:
            results = await self._transcribe_float32(audio)

            for result in results:
                if result.text and self._on_final:
                    await self._on_final(result.text, result.confidence)
        except Exception as exc:
            logger.error("Whisper decode error: {}", exc)
            self._audio_buffer = audio_buffer_snapshot + self._audio_buffer

    async def redecode_audio(self, audio_bytes: bytes) -> ASRDecodeResult | None:
        """Re-run Whisper on cached segment audio for ASR correction."""
        if self._engine != "whisper" or not self._model or not audio_bytes:
            return None

        audio = np.frombuffer(audio_bytes, dtype=np.float32)
        if audio.size == 0:
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

    async def _transcribe_float32(self, audio: np.ndarray) -> list[ASRDecodeResult]:
        segments, _info = await asyncio.to_thread(
            self._model.transcribe,
            audio,
            beam_size=5,
            language="en",
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

    async def shutdown(self) -> None:
        if self._model:
            del self._model
            self._model = None
        self._audio_buffer.clear()
        self._latest_input_audio_chunk = b""
        self._last_segment_audio_chunk = b""
        logger.info("ASR service shut down")
