"""上下文管理器 — 基于 Redis 的上下文窗口存储"""

import json
import time
from typing import Optional

import redis.asyncio as aioredis
from loguru import logger

from core.config import settings
from core.exceptions import ContextError
from models.segment import Segment, ContextWindow


class ContextManager:
    """上下文管理器

    使用 Redis 存储会话的上下文窗口，支持：
    - 会话生命周期管理
    - 段落级 CRUD
    - 滑动窗口获取
    - TTL 自动过期
    """

    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None

    async def initialize(self) -> None:
        """初始化 Redis 连接"""
        try:
            self._redis = aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            await self._redis.ping()
            logger.info(f"Redis connected: {settings.redis_url}")
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")
            raise ContextError(f"Redis init failed: {e}")

    async def init_session(self, session_id: str) -> None:
        """初始化新会话"""
        if not self._redis:
            raise ContextError("Redis not initialized")

        # 保存会话元数据
        await self._redis.hset(
            f"session:{session_id}:meta",
            mapping={
                "created_at": str(time.time()),
                "segment_count": "0",
            },
        )
        await self._redis.expire(
            f"session:{session_id}:meta",
            settings.segment_ttl_seconds,
        )
        logger.debug(f"Session initialized: {session_id}")

    async def add_segment(self, session_id: str, segment: Segment) -> None:
        """添加新段落到会话上下文窗口"""
        if not self._redis:
            raise ContextError("Redis not initialized")

        key = f"session:{session_id}:segments"

        # 序列化段落
        segment_data = {
            "id": segment.id,
            "text_asr": segment.text_asr,
            "confidence": segment.confidence,
            "text_translated": segment.text_translated,
            "status": segment.status,
            "timestamp": segment.timestamp,
            "revised_at": segment.revised_at or "",
            "revision_count": len(segment.revision_history),
        }

        # 追加到列表尾部
        await self._redis.rpush(key, json.dumps(segment_data))

        # 裁剪窗口大小（保留最近 N*2 条，留余量）
        max_len = settings.context_window_size * 2
        await self._redis.ltrim(key, -max_len, -1)

        # 设置 TTL
        await self._redis.expire(key, settings.segment_ttl_seconds)

    async def get_window(self, session_id: str) -> ContextWindow:
        """获取会话的上下文窗口"""
        if not self._redis:
            raise ContextError("Redis not initialized")

        key = f"session:{session_id}:segments"
        raw_segments = await self._redis.lrange(key, 0, -1)

        window = ContextWindow(
            session_id=session_id,
            window_size=settings.context_window_size,
        )

        for raw in raw_segments:
            data = json.loads(raw)
            seg = Segment(
                id=data["id"],
                text_asr=data["text_asr"],
                confidence=data["confidence"],
                text_translated=data.get("text_translated", ""),
                status=data.get("status", "draft"),
                timestamp=data.get("timestamp", 0),
                revised_at=data.get("revised_at") if data.get("revised_at") else None,
            )
            window.add_segment(seg)

        return window

    async def update_segment(self, session_id: str, segment: Segment) -> None:
        """更新段落（翻译完成后）"""
        if not self._redis:
            raise ContextError("Redis not initialized")

        key = f"session:{session_id}:segments"
        raw_list = await self._redis.lrange(key, 0, -1)

        for i, raw in enumerate(raw_list):
            data = json.loads(raw)
            if data["id"] == segment.id:
                data["text_translated"] = segment.text_translated
                data["status"] = segment.status
                data["revised_at"] = segment.revised_at or ""
                data["revision_count"] = len(segment.revision_history)
                await self._redis.lset(key, i, json.dumps(data))
                return

        logger.warning(f"Segment not found for update: {segment.id}")

    async def update_translation(
        self, session_id: str, segment_id: str, new_text: str
    ) -> None:
        """更新段落的翻译文本（修正引擎使用）"""
        if not self._redis:
            raise ContextError("Redis not initialized")

        key = f"session:{session_id}:segments"
        raw_list = await self._redis.lrange(key, 0, -1)

        for i, raw in enumerate(raw_list):
            data = json.loads(raw)
            if data["id"] == segment_id:
                data["text_translated"] = new_text
                data["status"] = "revised"
                await self._redis.lset(key, i, json.dumps(data))
                return

    async def update_source_text(
        self,
        session_id: str,
        segment_id: str,
        new_text: str,
    ) -> None:
        """Update the ASR source text for an existing segment."""
        if not self._redis:
            raise ContextError("Redis not initialized")

        key = f"session:{session_id}:segments"
        raw_list = await self._redis.lrange(key, 0, -1)

        for i, raw in enumerate(raw_list):
            data = json.loads(raw)
            if data["id"] == segment_id:
                data["text_asr"] = new_text
                data["status"] = "revised"
                await self._redis.lset(key, i, json.dumps(data))
                return

    async def save_audio_chunk(
        self,
        session_id: str,
        segment_id: str,
        audio_data: bytes,
    ) -> None:
        """Persist recent raw audio for future ASR correction."""
        if not self._redis:
            raise ContextError("Redis not initialized")

        key = f"session:{session_id}:audio:{segment_id}"
        await self._redis.set(key, audio_data.hex(), ex=settings.audio_ttl_seconds)

    async def get_audio_chunk(self, session_id: str, segment_id: str) -> Optional[bytes]:
        """Load raw audio bytes for a segment if still cached."""
        if not self._redis:
            raise ContextError("Redis not initialized")

        key = f"session:{session_id}:audio:{segment_id}"
        raw = await self._redis.get(key)
        if raw is None:
            return None
        return bytes.fromhex(raw)

    async def close_session(self, session_id: str) -> None:
        """关闭会话（保留数据到 TTL 过期）"""
        logger.debug(f"Session closed: {session_id}")

    async def shutdown(self) -> None:
        """关闭 Redis 连接"""
        if self._redis:
            await self._redis.close()
            logger.info("Redis connection closed")
