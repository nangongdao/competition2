"""WebSocket connection handler for live translation sessions."""

import asyncio
import hmac
import json
from collections import deque
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect, status
from loguru import logger

from core.config import settings
from core.pipeline import Pipeline
from services.asr_service import ASRService
from services.context_manager import ContextManager
from services.nmt_service import NMTService
from services.revision_service import RevisionService
from services.tts_service import TTSService


class ChunkRateLimiter:
    """滑动窗口音频帧速率限制器。

    限制每秒接收的音频帧数，防止恶意客户端用高频小帧
    打爆上游 ASR/翻译 API 配额（成本攻击面）。
    """

    def __init__(self, max_per_second: int) -> None:
        self._max_per_second = max_per_second
        self._timestamps: deque[float] = deque()

    def allow(self, now: float) -> bool:
        """判断当前时刻是否允许再接收一帧。

        Args:
            now: 当前单调时钟（秒）。

        Returns:
            True 允许；False 表示超出速率，应丢弃该帧。
        """
        while self._timestamps and now - self._timestamps[0] >= 1.0:
            self._timestamps.popleft()
        if len(self._timestamps) >= self._max_per_second:
            return False
        self._timestamps.append(now)
        return True


class WebSocketHandler:
    """Owns per-session pipelines and routes websocket messages."""

    def __init__(self) -> None:
        self._asr: Optional[ASRService] = None
        self._nmt: Optional[NMTService] = None
        self._ctx_manager: Optional[ContextManager] = None
        self._tts: Optional[TTSService] = None
        self._active_pipelines: dict[str, Pipeline] = {}
        self._reconnect_tokens: dict[str, str] = {}

    async def initialize(self) -> None:
        self._asr = ASRService()
        self._nmt = NMTService()
        self._ctx_manager = ContextManager()
        self._tts = TTSService()

        await self._asr.initialize()
        await self._nmt.initialize()
        await self._ctx_manager.initialize()
        await self._tts.initialize()

        logger.info("WebSocket handler initialized")

    @property
    def nmt_service(self) -> NMTService | None:
        """当前 NMT 服务实例（供摘要服务复用 LLM 客户端）。"""
        return self._nmt

    @property
    def ctx_manager(self) -> ContextManager | None:
        """当前上下文管理器实例。"""
        return self._ctx_manager

    def translation_memory_summary(self) -> dict[str, object]:
        """聚合所有活跃会话的翻译记忆库统计（V5.3 REST 端点用）。

        Returns:
            形如 {size, hits, misses, written, sessions} 的汇总统计。
        """
        total = {"size": 0, "hits": 0, "misses": 0, "written": 0}
        sessions: list[str] = []
        for session_id, pipeline in self._active_pipelines.items():
            stats = pipeline.translation_memory_stats()
            if stats is None:
                continue
            for key in total:
                total[key] += int(stats.get(key, 0))
            sessions.append(session_id)
        return {
            **total,
            "sessions": sessions,
            "threshold": settings.translation_memory_threshold,
        }

    def clear_translation_memory(self) -> int:
        """清空所有活跃会话的翻译记忆库。

        Returns:
            被清空的会话数。
        """
        cleared = 0
        for pipeline in self._active_pipelines.values():
            if pipeline.clear_translation_memory():
                cleared += 1
        return cleared

    def has_active_pipeline(self, session_id: str) -> bool:
        """返回会话当前是否已有活跃管线。

        用于重连鉴权：会话已存在时，重连必须携带有效令牌。
        """
        return session_id in self._active_pipelines

    async def get_session_window(self, session_id: str):
        """读取会话上下文窗口（供 REST 摘要端点使用）。

        会话片段由管线实时写入 Redis，这里直接读取持久化窗口；
        会话不存在或已过期（TTL 到）时返回 None。

        Args:
            session_id: 会话标识。

        Returns:
            会话上下文窗口；会话不存在或已过期时返回 None。
        """
        if self._ctx_manager is None:
            return None
        try:
            window = await self._ctx_manager.get_window(session_id)
        except Exception as exc:
            logger.warning("Failed to read persisted session window {}: {}", session_id, exc)
            return None
        return window if window.get_all() else None

    def issue_reconnect_token(self, session_id: str) -> str:
        """为会话签发重连令牌，随 SESSION_STARTED 消息下发给客户端。

        令牌是密码学安全的随机串，用于证明客户端确实是会话的所有者，
        避免攻击者枚举 session_id 后接管会话。
        """
        token = self._generate_token()
        self._reconnect_tokens[session_id] = token
        return token

    def verify_reconnect_token(self, session_id: str, token: str) -> bool:
        """校验重连令牌，使用常量时间比较避免时序侧信道。"""
        expected = self._reconnect_tokens.get(session_id)
        if not expected or not token:
            return False
        return hmac.compare_digest(expected, token)

    def _generate_token(self) -> str:
        import secrets

        return secrets.token_urlsafe(32)

    async def handle_connection(self, ws: WebSocket, session_id: str) -> None:
        await ws.accept()
        logger.info("WebSocket connected: {}", session_id)

        if not self._asr or not self._nmt or not self._ctx_manager or not self._tts:
            await ws.send_json({
                "type": "error",
                "code": "SERVICE_NOT_READY",
                "message": "Translation service is not initialized",
            })
            await ws.close()
            return

        existing = self._active_pipelines.get(session_id)
        if existing:
            logger.info("Replacing active pipeline for reconnecting session {}", session_id)
            await existing.stop()

        reconnect_token = self.issue_reconnect_token(session_id)
        pipeline = Pipeline(
            session_id=session_id,
            asr=self._asr.create_session(),
            nmt=self._nmt,
            ctx_manager=self._ctx_manager,
            revision=RevisionService(),
            tts=self._tts,
            reconnect_token=reconnect_token,
        )
        pipeline.set_on_message(lambda msg: self._send_message(ws, msg))
        pipeline.set_on_message_bytes(lambda data: self._send_bytes(ws, data))
        await pipeline.start()
        self._active_pipelines[session_id] = pipeline

        rate_limiter = ChunkRateLimiter(settings.audio_max_chunks_per_second)
        try:
            while True:
                raw = await ws.receive()

                if raw["type"] == "websocket.receive":
                    if "bytes" in raw:
                        should_close = await self._validate_audio_chunk(
                            ws, session_id, raw["bytes"], rate_limiter,
                        )
                        if should_close:
                            break
                        await pipeline.process_audio(raw["bytes"])
                    elif "text" in raw:
                        await self._handle_control_message(pipeline, raw["text"])
                elif raw["type"] == "websocket.disconnect":
                    break
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected: {}", session_id)
        except Exception as exc:
            logger.error("WebSocket error for {}: {}", session_id, exc)
        finally:
            await pipeline.stop()
            if self._active_pipelines.get(session_id) is pipeline:
                self._active_pipelines.pop(session_id, None)
            # 只清理本连接签发的令牌：若期间新连接已接管并签发新令牌，
            # 无条件 pop 会把新令牌删掉，锁死后续重连。
            if self._reconnect_tokens.get(session_id) == reconnect_token:
                self._reconnect_tokens.pop(session_id, None)

    async def _validate_audio_chunk(
        self,
        ws: WebSocket,
        session_id: str,
        chunk: bytes,
        rate_limiter: ChunkRateLimiter,
    ) -> bool:
        """校验单个音频帧，返回是否应关闭连接。

        校验维度：单帧大小、float32 对齐、发送速率。
        """
        if len(chunk) > settings.audio_max_chunk_bytes:
            logger.warning(
                "Session {} sent oversized audio chunk ({} bytes), closing",
                session_id, len(chunk),
            )
            await ws.close(code=status.WS_1009_MESSAGE_TOO_BIG)
            return True

        # float32 采样要求 4 字节倍数，避免 np.frombuffer 抛 ValueError 刷日志。
        # 未对齐帧也计入速率限制配额，防止恶意客户端用海量未对齐帧刷日志。
        if len(chunk) % 4 != 0:
            now = asyncio.get_running_loop().time()
            rate_limiter.allow(now)
            logger.warning("Session {} sent misaligned audio chunk, ignoring", session_id)
            return False

        now = asyncio.get_running_loop().time()
        if not rate_limiter.allow(now):
            logger.warning("Session {} exceeded audio rate limit", session_id)
            return False

        return False

    async def _handle_control_message(self, pipeline: Pipeline, text: str) -> None:
        try:
            msg = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON control message")
            return

        msg_type = msg.get("type")
        if msg_type == "pause":
            logger.debug("Pause received")
            return

        if msg_type == "resume":
            logger.debug("Resume received")
            return

        if msg_type == "config":
            language = msg.get("language")
            target = msg.get("target_language")
            style_preset = msg.get("style_preset")
            asr_hotwords_enabled = msg.get("asr_hotwords_enabled")
            await pipeline.update_config(
                language=language,
                target_language=target,
                style_preset=style_preset,
                asr_hotwords_enabled=asr_hotwords_enabled,
            )
            logger.info(
                "Config updated for {}: {} -> {} (style={})",
                pipeline.session_id,
                pipeline.language_config.source_language,
                pipeline.language_config.target_language,
                pipeline.nmt_style_preset,
            )
            return

        if msg_type == "set_glossary":
            entries = msg.get("entries")
            if isinstance(entries, list):
                await pipeline.update_glossary(entries)
                logger.info(
                    "Glossary update requested for session {} ({} entries)",
                    pipeline.session_id,
                    len(entries),
                )
            else:
                logger.warning("Invalid glossary payload: entries must be a list")
            return

        if msg_type == "manual_revise":
            logger.info("Manual revision requested for session {}", pipeline.session_id)
            await pipeline.trigger_manual_revision()
            return

        if msg_type == "request_diagnostics":
            await pipeline.emit_diagnostics()
            return

        logger.warning("Unknown message type: {}", msg_type)

    async def _send_message(self, ws: WebSocket, message: dict) -> None:
        try:
            await ws.send_json(message)
        except Exception as exc:
            logger.error("Failed to send message: {}", exc)

    async def _send_bytes(self, ws: WebSocket, payload: bytes) -> None:
        try:
            await ws.send_bytes(payload)
        except Exception as exc:
            logger.error("Failed to send bytes: {}", exc)

    def get_tts_stats(self) -> dict[str, object]:
        """汇总当前共享 TTS 服务的合成与缓存统计（供 REST 端点与前端面板）。"""
        if self._tts is None:
            return {"enabled": False, "engine": "off", "active": 0}
        return {
            "active": len(self._active_pipelines),
            **self._tts.diagnostics,
        }

    async def shutdown(self) -> None:
        for session_id, pipeline in list(self._active_pipelines.items()):
            await pipeline.stop()
            self._active_pipelines.pop(session_id, None)

        if self._asr:
            await self._asr.shutdown()
        if self._nmt:
            await self._nmt.shutdown()
        if self._ctx_manager:
            await self._ctx_manager.shutdown()
        if self._tts:
            await self._tts.shutdown()

        logger.info("WebSocket handler shut down")
