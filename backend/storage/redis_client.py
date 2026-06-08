"""Redis 客户端封装

提供更高级的 Redis 操作接口，用于上下文存储之外的通��缓存需求。
"""

import redis.asyncio as aioredis
from typing import Optional, Any
from loguru import logger

from core.config import settings


class RedisClient:
    """Redis 客户端封装"""

    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None

    async def connect(self) -> None:
        """建立 Redis 连接"""
        self._redis = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            protocol=settings.redis_protocol,
        )
        await self._redis.ping()
        logger.info("Redis client connected")

    async def get(self, key: str) -> Optional[str]:
        """获取键值"""
        if not self._redis:
            return None
        return await self._redis.get(key)

    async def set(self, key: str, value: str, ttl: int = 0) -> None:
        """设置键值"""
        if not self._redis:
            return
        await self._redis.set(key, value, ex=ttl if ttl > 0 else None)

    async def close(self) -> None:
        """关闭连接"""
        if self._redis:
            await self._redis.close()
