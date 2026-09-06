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
from api.router import (
    router,
    set_ws_handler,
    set_terminal_bridge,
    set_summary_service,
)
from api.websocket_handler import WebSocketHandler
from api.middleware import logging_middleware
from services.collaboration import CollaborationService, set_collaboration_service
from services.cost_service import CostService, set_cost_service
from services.glossary_manager import GlossaryManager, set_glossary_manager
from services.session_data_service import (
    SessionDataService,
    set_session_data_service,
)
from services.subscription import SubscriptionService, set_subscription_service
from services.terminal_bridge import TerminalBridge
from services.session_summary import SessionSummaryService


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

    # 初始化内置终端桥接
    terminal_bridge = TerminalBridge()
    set_terminal_bridge(terminal_bridge)
    logger.info("Terminal bridge initialized")

    # 初始化会话学习摘要服务（复用 WebSocket 处理器的 NMT 客户端）
    summary_service = SessionSummaryService()
    summary_service.attach_nmt(ws_handler.nmt_service)
    set_summary_service(summary_service)
    logger.info("Session summary service initialized")

    # 初始化术语库管理（V5.1）：加载本地持久化术语表
    glossary_manager = GlossaryManager()
    set_glossary_manager(glossary_manager)
    logger.info("Glossary manager initialized ({} entries)", glossary_manager.size)

    # 初始化翻译记忆库持久化存储（V5.3 生产化）：跨会话累积翻译记忆
    from services.translation_memory_store import (
        TranslationMemoryStore,
        set_tm_store,
    )

    tm_store = TranslationMemoryStore()
    set_tm_store(tm_store)
    logger.info(
        "Translation memory store initialized ({} entries)",
        tm_store.size(),
    )

    # 初始化多人协作翻译服务（V5.2）：房间管理 + 协作修正广播
    collaboration_service = CollaborationService()
    set_collaboration_service(collaboration_service)
    logger.info("Collaboration service initialized")

    # 初始化付费订阅与配额服务（V5.5）：套餐 + 每日句数计量
    subscription_service = SubscriptionService()
    set_subscription_service(subscription_service)
    logger.info("Subscription service initialized (plan {})", subscription_service.plan)

    # 初始化商用成本模型服务（用量计量 + 成本估算 + 熔断软上限）
    cost_service = CostService()
    set_cost_service(cost_service)
    logger.info("Cost service initialized ({} sessions)", cost_service.snapshot().get("total_sessions"))

    # 初始化会话数据生命周期服务（阶段 10）：会话台账 + 隐私清理
    session_data_service = SessionDataService()
    set_session_data_service(session_data_service)
    purged = session_data_service.purge_expired()
    logger.info(
        "Session data service initialized ({} sessions, purged {})",
        session_data_service.size,
        purged,
    )

    yield

    # ---- 关闭阶段 ----
    logger.info("Shutting down services...")
    await terminal_bridge.shutdown()
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
    allow_origins=settings.allowed_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
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
        # 本地服务不在反向代理后，禁用 X-Forwarded-* 覆写，
        # 防止 loopback 校验被伪造头绕过。
        proxy_headers=False,
        # WebSocket 单帧上限 64KB，与后端音频帧校验保持一致。
        ws_max_size=64 * 1024,
    )


if __name__ == "__main__":
    main()