"""AI 同声传译助手 — 后端入口

FastAPI 应用主入口，负责：
- 初始化所有服务
- 注册路由和中间件
- 管理应用生命周期
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from loguru import logger

from core.config import settings
from api.router import router, set_ws_handler
from api.websocket_handler import WebSocketHandler
from api.middleware import logging_middleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # ---- 启动阶段 ----
    logger.info("=" * 50)
    logger.info("AI 同声传译助手 — 后端服务启动中...")
    logger.info("=" * 50)

    # 初始化 WebSocket 处理器
    ws_handler = WebSocketHandler()
    await ws_handler.initialize()
    set_ws_handler(ws_handler)
    logger.info("All services initialized successfully")

    yield

    # ---- 关闭阶段 ----
    logger.info("Shutting down services...")
    await ws_handler.shutdown()
    logger.info("Backend service stopped")


app = FastAPI(
    title="AI 同声传译助手",
    description="实时英语→中文字幕同传服务",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 请求日志中间件
app.middleware("http")(logging_middleware)

# 注册路由
app.include_router(router, prefix="/api/v1")


def main():
    """启动服务"""
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info",
    )


if __name__ == "__main__":
    main()