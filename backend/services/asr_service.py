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
from services.asr_text_postprocess import postprocess_asr_text
from services.language_config import normalize_source_language, whisper_language_code


#: 全局开关（阶段 2 后处理）：关闭时保持原文直通，不影响现有链路
_ASR_POSTPROCESS_ENABLED = settings.asr_text_postprocess_enabled


def _maybe_postprocess(text: str, *, language: str | None = None) -> str:
    """按配置决定是否对 ASR 文本做轻量规范化。"""
    if not _ASR_POSTPROCESS_ENABLED:
        return text
    return postprocess_asr_text(text, language=language)


FinalCallback = Callable[[str, float, str | None], Awaitable[None]]
PartialCallback = Callable[[str], Awaitable[None]]


@dataclass(frozen=True)
class ASRDecodeResult:
    text: str
    confidence: float
    #: 自动检测模式（source_language=auto）下，ASR 返回的检测语言代码；
    #: 未检测或非 auto 模式时为 None。
    detected_language: str | None = None


class _SharedModelState:
    """多个会话共享的 ASR 模型 / 客户端 / VAD 资源持有者。

    在 TD-3 的多会话共享场景下，父服务与所有 `create_session()` 派生的
    子会话都指向同一个 `_SharedModelState` 实例。底层模型（Whisper）或
    客户端（OpenAI）只被加载一次，并通过引用计数决定何时真正释放，
    避免某个会话提前 shutdown 时误删共享模型导致其它会话崩溃。
    """

    def __init__(self) -> None:
        self.model = None
        self.client = None
        self.vad: Optional[SileroVoiceActivityDetector] = None
        self._refcount = 1

    def acquire(self) -> None:
        """新增一个共享该模型的会话引用。"""
        self._refcount += 1

    def release(self) -> None:
        """释放一个会话引用；引用归零时清空底层资源。"""
        if self._refcount <= 0:
            return
        self._refcount -= 1
        if self._refcount == 0:
            self._clear_resources()

    @property
    def refcount(self) -> int:
        return self._refcount

    def _clear_resources(self) -> None:
        """引用归零后真正释放底层模型 / 客户端 / VAD。"""
        if self.model is not None:
            del self.model
            self.model = None
        self.client = None
        self.vad = None
        logger.info("Shared ASR resources released (refcount reached zero)")


class ASRService:
    def __init__(self) -> None:
        self._engine = settings.asr_engine
        #: 该会话实际使用的模型/客户端/VAD 持有者。父服务自有，子会话共享。
        self._shared = _SharedModelState()
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
        #: 术语热词（阶段 2）：从术语表 source 生成，注入 ASR 提升专名识别
        self._hotwords: list[str] = []
        self._hotwords_enabled = settings.asr_hotwords_enabled

    @property
    def _model(self):
        """兼容旧访问：映射到共享持有者的模型。"""
        return self._shared.model

    @_model.setter
    def _model(self, value) -> None:
        self._shared.model = value

    @property
    def _client(self):
        """兼容旧访问：映射到共享持有者的客户端。"""
        return self._shared.client

    @_client.setter
    def _client(self, value) -> None:
        self._shared.client = value

    @property
    def _vad(self):
        """兼容旧访问：映射到共享持有者的 VAD。"""
        return self._shared.vad

    @_vad.setter
    def _vad(self, value) -> None:
        self._shared.vad = value

    def set_on_partial(self, callback: PartialCallback) -> None:
        self._on_partial = callback

    def set_on_final(self, callback: FinalCallback) -> None:
        self._on_final = callback

    def set_language(self, source_language: str) -> None:
        self._source_language = normalize_source_language(source_language)

    def set_hotwords(self, hotwords: list[str]) -> None:
        """设置 ASR 热词列表（阶段 2：术语热词注入）。

        热词来自术语表 source 字段：只取长度合适、非空且不重复的条目，
        避免超长/含标点的噪音污染解码。

        Args:
            hotwords: 热词字符串列表（已由调用方裁剪长度）。
        """
        max_term_length = settings.asr_hotwords_max_term_length
        seen: set[str] = set()
        cleaned: list[str] = []
        for term in hotwords:
            stripped = (term or "").strip()
            if not stripped:
                continue
            if len(stripped) > max_term_length:
                continue
            key = stripped.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(stripped)
        self._hotwords = cleaned[: settings.asr_hotwords_max_terms]

    def set_hotwords_enabled(self, enabled: bool) -> None:
        """开关热词注入（运行时切换，无需重建会话）。"""
        self._hotwords_enabled = bool(enabled)

    @property
    def hotwords(self) -> list[str]:
        """当前生效的热词列表（快照）。"""
        return list(self._hotwords)

    @property
    def hotwords_enabled(self) -> bool:
        """热词注入当前是否开启。"""
        return self._hotwords_enabled

    def _hotwords_text(self) -> str:
        """把热词列表拼成 ASR 提示文本（逗号分隔）。"""
        if not self._hotwords_enabled or not self._hotwords:
            return ""
        return ", ".join(self._hotwords)

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
        """按配置构造分段器；禁用或构造失败时返回 None（退回固定窗口）。

        V2.4 参数化：使用 VAD 专属配置控制切分——
        vad_min_speech_ms 映射最短片段、vad_min_silence_ms 映射断句静音边界、
        vad_max_sentence_s 映射最大句长（强制断句）。
        """
        if not settings.adaptive_segmenter_enabled:
            return None
        return AdaptiveSegmenter(
            sample_rate=self._sample_rate,
            min_segment_ms=settings.vad_min_speech_ms,
            max_segment_ms=int(settings.vad_max_sentence_s * 1000),
            silence_boundary_ms=settings.vad_min_silence_ms,
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
                text = _maybe_postprocess(result.text, language=self._source_language)
                await self._on_final(text, result.confidence, result.detected_language)
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
                    text = _maybe_postprocess(result.text, language=self._source_language)
                    await self._on_final(text, result.confidence, result.detected_language)
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
        text = postprocess_asr_text(text, language=self._source_language) if _ASR_POSTPROCESS_ENABLED else text

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
            "response_format": "verbose_json",
        }
        if language:
            request["language"] = language
        # 阶段 2：术语热词注入 —— OpenAI 兼容转录接口通过 prompt 参数提示专名
        hotwords_text = self._hotwords_text()
        if hotwords_text:
            request["prompt"] = hotwords_text

        response = await self._client.audio.transcriptions.create(**request)
        text = extract_transcription_text(response)
        if not text:
            return None
        text = postprocess_asr_text(text, language=self._source_language) if _ASR_POSTPROCESS_ENABLED else text
        detected = self._extract_detected_language(response)
        return ASRDecodeResult(text=text, confidence=0.0, detected_language=detected)

    def _extract_detected_language(self, response: object) -> str | None:
        """从 verbose_json 响应中提取 Whisper 检测的语言代码。

        OpenAI Whisper 在 ``response_format=verbose_json`` 时返回顶层
        ``language`` 字段（如 ``"english"`` / ``"japanese"``）。本地
        faster-whisper 的 ``TranscriptionInfo.language`` 也是这种格式。

        Args:
            response: ASR 响应对象（dict 或带属性对象）。

        Returns:
            Whisper 风格的语言名（小写）；未检测到返回 None。
        """
        if isinstance(response, dict):
            value = response.get("language")
        else:
            value = getattr(response, "language", None)
        if not isinstance(value, str):
            return None
        stripped = value.strip().lower()
        return stripped or None

    async def _transcribe_float32(self, audio: np.ndarray) -> list[ASRDecodeResult]:
        hotwords_text = self._hotwords_text()
        segments, info = await asyncio.to_thread(
            self._model.transcribe,
            audio,
            beam_size=5,
            language=whisper_language_code(self._source_language),
            vad_filter=self._vad_enabled,
            without_timestamps=True,
            # 阶段 2：术语热词注入 —— faster-whisper 原生 hotwords 参数
            hotwords=hotwords_text or None,
        )

        # auto 模式下记录 Whisper 检测到的语言（info.language 如 "en"）
        detected: str | None = None
        if self._source_language == "auto":
            detected = getattr(info, "language", None) or None

        results: list[ASRDecodeResult] = []
        for segment in segments:
            text = segment.text.strip()
            if text:
                results.append(ASRDecodeResult(
                    text=text,
                    confidence=segment.avg_logprob,
                    detected_language=detected,
                ))
        return results

    def get_last_audio_chunk(self) -> bytes:
        return self._last_segment_audio_chunk or self._latest_input_audio_chunk

    def create_session(self) -> ASRService:
        """Create isolated stream state that shares the initialized model.

        派生子会话：与父服务共享同一个底层模型/客户端/VAD 持有者，
        并对共享引用 +1，保证子会话在 `shutdown()` 时不会误删仍被
        其它会话引用的共享模型。
        """
        service = ASRService()
        service._shared = self._shared
        self._shared.acquire()
        service._source_language = self._source_language
        service._segmenter = service._build_segmenter()
        # 子会话继承热词状态（术语表为全局语义，会话间保持一致）
        service._hotwords = list(self._hotwords)
        service._hotwords_enabled = self._hotwords_enabled
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
        """关闭会话并释放资源。

        引用计数的共享持有者会在最后一个引用被释放时才真正清空
        底层模型，从而保证多会话共享模型时不会互相误删。

        父服务通过 `initialize()` 持有初始引用，子会话通过
        `create_session()` 各 +1；无论父服务还是子会话，
        `shutdown()` 都只释放自己持有的一份引用。
        """
        self._shared.release()
        self._audio_buffer.clear()
        self._latest_input_audio_chunk = b""
        self._last_segment_audio_chunk = b""
        if self._segmenter is not None:
            self._segmenter.reset()
        logger.info("ASR service shut down (refcount={})", self._shared.refcount)


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
