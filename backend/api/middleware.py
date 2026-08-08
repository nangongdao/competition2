"""API 中间件"""

import time

from fastapi import Request
from loguru import logger


async def logging_middleware(request: Request, call_next):
    """请求日志中间件"""
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    logger.info(
        f"{request.method} {request.url.path} "
        f"→ {response.status_code} ({duration:.3f}s)"
    )
    return response