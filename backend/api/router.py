"""FastAPI 路由定义"""

import secrets
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request, WebSocket, status
from loguru import logger
from pydantic import BaseModel, ConfigDict

from api.websocket_handler import WebSocketHandler
from core.config import settings
from services.local_settings import (
    create_settings_snapshot,
    read_local_settings,
    save_local_settings_update,
)

router = APIRouter()
LOOPBACK_CLIENT_HOSTS = {"127.0.0.1", "::1", "localhost"}

# 全局 WebSocket 处理器（在 main.py 中初始化）
_ws_handler: WebSocketHandler | None = None


class LocalTranslationSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    engine: str | None = None
    model: str | None = None
    openaiBaseUrl: str | None = None
    openaiApiKey: str | None = None
    anthropicApiKey: str | None = None
    clearOpenaiApiKey: bool | None = None
    clearAnthropicApiKey: bool | None = None


class LocalAsrSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str | None = None
    openaiBaseUrl: str | None = None
    openaiApiKey: str | None = None
    clearOpenaiApiKey: bool | None = None


class LocalRuntimeSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    asrProfile: str | None = None
    sourceLanguage: str | None = None


class LocalSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    uiLanguage: str | None = None
    translation: LocalTranslationSettingsUpdate | None = None
    asr: LocalAsrSettingsUpdate | None = None
    runtime: LocalRuntimeSettingsUpdate | None = None


def require_loopback_client(request: Request) -> None:
    client_host = request.client.host if request.client else ""
    if client_host not in LOOPBACK_CLIENT_HOSTS:
        raise HTTPException(
            status_code=403,
            detail="local settings require a loopback client",
        )


def get_ws_handler() -> WebSocketHandler | None:
    """获取 WebSocket 处理器实例"""
    return _ws_handler


def set_ws_handler(handler: WebSocketHandler) -> None:
    """设置 WebSocket 处理器实例"""
    global _ws_handler
    _ws_handler = handler


def _is_allowed_ws_origin(origin: str | None) -> bool:
    """校验 WebSocket 握手的 Origin 头。

    WebSocket 不受同源策略保护，必须服务端主动校验，
    否则任意网站都可连接本地服务（CSWSH）。

    Args:
        origin: 握手请求中的 Origin 头，可能为 None（非浏览器客户端）。

    Returns:
        是否允许该来源建立连接。
    """
    # 非浏览器客户端（如测试工具）不带 Origin，桌面场景可放行。
    if origin is None:
        return True

    if origin in settings.allowed_origin_list:
        return True

    # 额外放行 Electron 的 file:// 来源
    parsed = urlparse(origin)
    return parsed.scheme == "file"


async def _reject_unauthorized_ws(ws: WebSocket) -> None:
    """拒绝未授权的 WebSocket 握手。"""
    await ws.close(code=status.WS_1008_POLICY_VIOLATION)


@router.get("/health")
async def health_check():
    """健康检查端点"""
    return {"status": "ok", "service": "AI同声传译助手"}


@router.get("/settings/local")
async def get_local_settings(request: Request):
    """Read the local browser/desktop settings snapshot without exposing secrets."""
    require_loopback_client(request)
    settings = read_local_settings()
    return {
        "success": True,
        "reason": "local settings loaded",
        "settings": create_settings_snapshot(settings),
    }


@router.put("/settings/local")
async def save_local_settings(request: Request, update: LocalSettingsUpdate):
    """Save local browser/desktop settings while preserving write-only secrets."""
    require_loopback_client(request)
    try:
        settings = save_local_settings_update(update.model_dump())
    except Exception as error:
        logger.error("Failed to save local settings: {}", error)
        return {
            "success": False,
            "reason": "failed to save local settings",
        }

    return {
        "success": True,
        "reason": "local settings saved",
        "settings": create_settings_snapshot(settings),
    }


@router.websocket("/ws/translate")
async def websocket_translate(ws: WebSocket):
    """WebSocket 翻译端点

    客户端通过此端点建立 WebSocket 连接，
    发送音频数据并接收翻译结果。
    """
    if not _is_allowed_ws_origin(ws.headers.get("origin")):
        logger.warning("Rejected websocket from origin {}", ws.headers.get("origin"))
        await _reject_unauthorized_ws(ws)
        return

    handler = get_ws_handler()
    if not handler:
        await ws.accept()
        await ws.send_json({
            "type": "error",
            "code": "SERVICE_NOT_READY",
            "message": "Translation service is not initialized",
        })
        await ws.close()
        return

    # 使用密码学安全的随机串生成会话 ID（192 bit 熵，不可枚举）
    session_id = secrets.token_urlsafe(24)
    await handler.handle_connection(ws, session_id)


@router.websocket("/ws/translate/{session_id}")
async def websocket_translate_with_session(ws: WebSocket, session_id: str):
    """WebSocket 翻译端点（带指定会话 ID，用于重连）

    重连必须提供首次连接时下发的 reconnect_token，
    否则任何人猜到 session_id 就能接管会话。
    """
    if not _is_allowed_ws_origin(ws.headers.get("origin")):
        logger.warning("Rejected websocket from origin {}", ws.headers.get("origin"))
        await _reject_unauthorized_ws(ws)
        return

    handler = get_ws_handler()
    if not handler:
        await ws.accept()
        await ws.send_json({
            "type": "error",
            "code": "SERVICE_NOT_READY",
            "message": "Translation service is not initialized",
        })
        await ws.close()
        return

    # 会话已存在时，重连必须携带有效令牌；首次连接（无活跃管线）放行。
    if handler.has_active_pipeline(session_id):
        token = ws.query_params.get("token", "")
        if not handler.verify_reconnect_token(session_id, token):
            logger.warning("Rejected reconnect with invalid token for session {}", session_id)
            await _reject_unauthorized_ws(ws)
            return

    await handler.handle_connection(ws, session_id)
