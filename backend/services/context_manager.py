"""Redis-backed context window and per-session audio cache."""

from __future__ import annotations

import json
import time
from typing import Optional

import redis.asyncio as aioredis
from loguru import logger

from core.config import settings
from core.exceptions import ContextError
from models.segment import ContextWindow, Segment


class ContextManager:
    """Stores session context windows, metadata, and cached segment audio."""

    def __init__(self) -> None:
        self._redis: Optional[aioredis.Redis] = None

    async def initialize(self) -> None:
        """Initialize the Redis connection."""
        try:
            self._redis = aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            await self._redis.ping()
            logger.info("Redis connected: {}", settings.redis_url)
        except Exception as exc:
            logger.error("Redis connection failed: {}", exc)
            raise ContextError(f"Redis init failed: {exc}") from exc

    async def init_session(self, session_id: str) -> int:
        """Initialize metadata and return the reconnect count for the session."""
        if not self._redis:
            raise ContextError("Redis not initialized")

        meta_key = f"session:{session_id}:meta"
        exists = bool(await self._redis.exists(meta_key))

        if not exists:
            await self._redis.hset(
                meta_key,
                mapping={
                    "created_at": str(time.time()),
                    "segment_count": "0",
                    "reconnect_count": "0",
                },
            )
            reconnect_count = 0
        else:
            reconnect_count = await self._redis.hincrby(meta_key, "reconnect_count", 1)

        await self._redis.hset(meta_key, "last_connected_at", str(time.time()))
        await self._redis.expire(meta_key, settings.segment_ttl_seconds)
        logger.debug("Session initialized: {}", session_id)
        return int(reconnect_count)

    async def next_segment_index(self, session_id: str) -> int:
        """Reserve a stable segment index for reconnect-safe segment IDs."""
        if not self._redis:
            raise ContextError("Redis not initialized")

        meta_key = f"session:{session_id}:meta"
        next_value = await self._redis.hincrby(meta_key, "segment_count", 1)
        await self._redis.expire(meta_key, settings.segment_ttl_seconds)
        return int(next_value) - 1

    async def add_segment(self, session_id: str, segment: Segment) -> None:
        """Append a segment to the session context window."""
        if not self._redis:
            raise ContextError("Redis not initialized")

        key = f"session:{session_id}:segments"
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

        await self._redis.rpush(key, json.dumps(segment_data))
        max_len = settings.context_window_size * 2
        await self._redis.ltrim(key, -max_len, -1)
        await self._redis.expire(key, settings.segment_ttl_seconds)

    async def get_window(self, session_id: str) -> ContextWindow:
        """Return the current sliding context window for a session."""
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
        """Update segment state after translation finalization."""
        if not self._redis:
            raise ContextError("Redis not initialized")

        key = f"session:{session_id}:segments"
        raw_list = await self._redis.lrange(key, 0, -1)

        for index, raw in enumerate(raw_list):
            data = json.loads(raw)
            if data["id"] == segment.id:
                data["text_translated"] = segment.text_translated
                data["status"] = segment.status
                data["revised_at"] = segment.revised_at or ""
                data["revision_count"] = len(segment.revision_history)
                await self._redis.lset(key, index, json.dumps(data))
                return

        logger.warning("Segment not found for update: {}", segment.id)

    async def update_translation(
        self,
        session_id: str,
        segment_id: str,
        new_text: str,
    ) -> None:
        """Update translated text for an existing segment."""
        if not self._redis:
            raise ContextError("Redis not initialized")

        key = f"session:{session_id}:segments"
        raw_list = await self._redis.lrange(key, 0, -1)

        for index, raw in enumerate(raw_list):
            data = json.loads(raw)
            if data["id"] == segment_id:
                data["text_translated"] = new_text
                data["status"] = "revised"
                await self._redis.lset(key, index, json.dumps(data))
                return

    async def update_source_text(
        self,
        session_id: str,
        segment_id: str,
        new_text: str,
    ) -> None:
        """Update ASR source text for an existing segment."""
        if not self._redis:
            raise ContextError("Redis not initialized")

        key = f"session:{session_id}:segments"
        raw_list = await self._redis.lrange(key, 0, -1)

        for index, raw in enumerate(raw_list):
            data = json.loads(raw)
            if data["id"] == segment_id:
                data["text_asr"] = new_text
                data["status"] = "revised"
                await self._redis.lset(key, index, json.dumps(data))
                return

    async def save_audio_chunk(
        self,
        session_id: str,
        segment_id: str,
        audio_data: bytes,
    ) -> None:
        """Persist raw segment audio for future ASR correction."""
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
        """Close the active connection while keeping session data until TTL expiry."""
        logger.debug("Session closed: {}", session_id)

    async def shutdown(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            logger.info("Redis connection closed")
