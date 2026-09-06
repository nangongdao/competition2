"""TTS 语音合成服务。

支持的引擎：
- ``edge``：edge-tts（微软 Edge 神经网络语音，免费、无需 API key，质量好）
- ``openai``：OpenAI 兼容 TTS API（需要配置 base_url 与 api_key）
- ``off``：禁用后端合成

设计约束：
- 合成是 CPU/网络密集型操作，必须在线程池执行，避免阻塞事件循环。
- 会话内按文本缓存合成结果，重复片段（如重连、修正）不重复请求上游。
- 合成失败不抛断管线：返回空音频并在诊断中记录失败计数。
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

from loguru import logger

from core.config import settings


class TTSService:
    """语音合成服务（edge-tts / OpenAI 兼容）。"""

    def __init__(self) -> None:
        self._engine = settings.tts_engine
        self._voice = settings.tts_voice
        self._rate = settings.tts_rate
        self._volume = settings.tts_volume
        self._openai_model = settings.tts_openai_model
        self._openai_base_url = settings.tts_openai_base_url
        self._openai_api_key = settings.tts_openai_api_key
        self._cache: dict[str, bytes] = {}
        self._cache_hits = 0
        self._disk_hits = 0
        self._synthesized = 0
        self._failed = 0
        self._initialized = False
        self._cache_dir = self._resolve_cache_dir(settings.tts_cache_dir)

    @staticmethod
    def _resolve_cache_dir(raw: str) -> Path | None:
        """解析磁盘缓存目录；目录不可写或为空时返回 None（仅用内存缓存）。"""
        if not raw:
            return None
        try:
            path = Path(raw)
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".probe"
            probe.write_bytes(b"ok")
            probe.unlink()
            return path
        except OSError as exc:
            logger.warning("TTS disk cache directory unavailable, using memory only: {}", exc)
            return None

    @property
    def engine(self) -> str:
        return self._engine

    @property
    def enabled(self) -> bool:
        return self._engine != "off"

    @property
    def voice(self) -> str:
        return self._voice

    @property
    def rate(self) -> str:
        return self._rate

    @property
    def volume(self) -> str:
        return self._volume

    def update_settings(
        self,
        *,
        voice: str | None = None,
        rate: str | None = None,
        volume: str | None = None,
    ) -> None:
        """运行时更新语音/语速/音量（前端 config 消息调用）。

        语音/语速/音量变化会影响合成结果，因此同时清空内存与磁盘缓存，避免旧结果误命中。
        """
        changed = False
        if voice is not None and voice != self._voice:
            self._voice = voice
            changed = True
        if rate is not None and rate != self._rate:
            self._rate = rate
            changed = True
        if volume is not None and volume != self._volume:
            self._volume = volume
            changed = True
        if changed:
            self.clear_cache()
            logger.info(
                "TTS settings updated (voice={}, rate={}, volume={})",
                self._voice, self._rate, self._volume,
            )

    async def initialize(self) -> None:
        """预热：校验引擎配置（不发起网络请求，仅检查依赖与配置）。"""
        if self._engine == "off":
            logger.info("TTS service disabled (tts_engine=off)")
            self._initialized = True
            return
        if self._engine == "openai" and not self._openai_api_key:
            logger.warning(
                "TTS engine=openai but no API key configured; synthesis will fail gracefully"
            )
        try:
            import importlib

            importlib.import_module("edge_tts" if self._engine == "edge" else "httpx")
        except ImportError as exc:
            logger.error("TTS engine {} missing dependency: {}", self._engine, exc)
        self._initialized = True
        logger.info(
            "TTS service initialized (engine={}, voice={}, rate={})",
            self._engine, self._voice, self._rate,
        )

    async def shutdown(self) -> None:
        """释放资源（清空内存缓存；磁盘缓存保留供跨会话复用）。"""
        self.clear_cache()
        self._initialized = False
        logger.info("TTS service shut down")

    @property
    def disk_cache_file_count(self) -> int:
        """磁盘缓存目录中的缓存文件数（跨会话复用产物）。"""
        if self._cache_dir is None:
            return 0
        try:
            return sum(1 for p in self._cache_dir.iterdir() if p.is_file())
        except OSError:
            return 0

    @property
    def diagnostics(self) -> dict[str, object]:
        """合成统计（供会话诊断与前端展示）。"""
        return {
            "engine": self._engine,
            "voice": self._voice,
            "rate": self._rate,
            "volume": self._volume,
            "enabled": self.enabled,
            "cacheSize": len(self._cache),
            "cacheHits": self._cache_hits,
            "diskHits": self._disk_hits,
            "diskCacheFiles": self.disk_cache_file_count,
            "synthesized": self._synthesized,
            "failed": self._failed,
        }

    async def synthesize(self, text: str, language: str = "zh-CN") -> bytes:
        """将文本合成为 MP3 音频字节。

        Args:
            text: 要朗读的译文文本。
            language: 目标语言（用于选择语音；edge-tts 使用 voice 参数）。

        Returns:
            MP3 音频字节；失败或输入为空时返回空字节（不中断管线）。
        """
        if not self.enabled:
            return b""

        normalized = text.strip()
        if not normalized:
            return b""

        cache_key = self._cache_key(normalized, language)
        # 1) 内存缓存
        cached = self._cache.get(cache_key)
        if cached is not None:
            self._cache_hits += 1
            return cached

        # 2) 磁盘缓存（跨会话复用）
        disk = self._read_disk_cache(cache_key)
        if disk is not None:
            self._disk_hits += 1
            self._remember(cache_key, disk)
            return disk

        try:
            audio = await asyncio.to_thread(self._synthesize_blocking, normalized, language)
        except Exception as exc:
            self._failed += 1
            logger.error("TTS synthesis failed: {}", exc)
            return b""

        # 仅缓存非空结果，避免把失败也缓存住
        if audio:
            self._synthesized += 1
            self._remember(cache_key, audio)
        return audio

    def clear_cache(self) -> None:
        """清空合成缓存（会话结束时调用；磁盘缓存保留供跨会话复用）。"""
        self._cache.clear()
        self._cache_hits = 0
        self._disk_hits = 0
        self._synthesized = 0
        self._failed = 0

    def _remember(self, cache_key: str, audio: bytes) -> None:
        """写入内存缓存，并按容量上限同步到磁盘。"""
        if len(self._cache) < settings.tts_cache_max_entries:
            self._cache[cache_key] = audio
        if self._cache_dir is not None:
            self._write_disk_cache(cache_key, audio)

    def _disk_path(self, cache_dir: Path, cache_key: str) -> Path:
        digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
        return cache_dir / f"{digest}.mp3"

    def _read_disk_cache(self, cache_key: str) -> bytes | None:
        if self._cache_dir is None:
            return None
        path = self._disk_path(self._cache_dir, cache_key)
        try:
            return path.read_bytes()
        except OSError:
            return None

    def _write_disk_cache(self, cache_key: str, audio: bytes) -> None:
        if self._cache_dir is None:
            return
        try:
            self._disk_path(self._cache_dir, cache_key).write_bytes(audio)
            self._enforce_disk_cap()
        except OSError as exc:
            logger.warning("TTS disk cache write failed: {}", exc)

    def _enforce_disk_cap(self) -> None:
        """磁盘缓存超限时清理最旧文件，防止无限膨胀。"""
        if self._cache_dir is None:
            return
        try:
            files = [p for p in self._cache_dir.iterdir() if p.is_file()]
            if len(files) <= settings.tts_cache_max_files:
                return
            # 按修改时间最旧优先清理
            files.sort(key=lambda p: p.stat().st_mtime)
            for stale in files[: len(files) - settings.tts_cache_max_files]:
                stale.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("TTS disk cache cap enforcement failed: {}", exc)

    def _synthesize_blocking(self, text: str, language: str) -> bytes:
        if self._engine == "openai":
            return self._synthesize_openai(text, language)
        if self._engine == "edge":
            return self._synthesize_edge(text, language)
        raise RuntimeError(f"Unknown TTS engine: {self._engine}")

    def _synthesize_openai(self, text: str, language: str) -> bytes:
        """OpenAI 兼容 TTS（同步调用，在线程池执行）。"""
        import httpx

        if not self._openai_api_key:
            raise RuntimeError("OpenAI TTS requires an API key")

        url = f"{self._openai_base_url.rstrip('/')}/audio/speech"
        headers = {
            "Authorization": f"Bearer {self._openai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._openai_model,
            "voice": self._voice,
            "input": text,
            "response_format": "mp3",
        }

        with httpx.Client(timeout=settings.tts_timeout_seconds) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.content

    def _synthesize_edge(self, text: str, language: str) -> bytes:
        """edge-tts 合成（同步调用，在线程池执行）。"""
        import edge_tts

        async def _stream() -> bytes:
            communicate = edge_tts.Communicate(
                text, voice=self._voice, rate=self._rate, volume=self._volume
            )
            chunks: list[bytes] = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    chunks.append(chunk["data"])
            return b"".join(chunks)

        return asyncio.run(_stream())

    def _cache_key(self, text: str, language: str) -> str:
        digest = hashlib.sha256(
            f"{self._engine}|{self._voice}|{self._rate}|{self._volume}|{language}|{text}".encode("utf-8")
        ).hexdigest()
        return f"{language}:{digest}"
