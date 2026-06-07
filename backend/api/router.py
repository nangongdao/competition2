"""FastAPI 路由定义"""

import uuid

from fastapi import APIRouter, HTTPException, Request, WebSocket
from loguru import logger
from pydantic import BaseModel, ConfigDict

from api.websocket_handler import WebSocketHandler
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


class LocalRuntimeSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    asrProfile: str | None = None
    sourceLanguage: str | None = None


class LocalSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    uiLanguage: str | None = None
    translation: LocalTranslationSettingsUpdate | None = None
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

    # 生成会话 ID
    session_id = str(uuid.uuid4())[:8]
    await handler.handle_connection(ws, session_id)


@router.websocket("/ws/translate/{session_id}")
async def websocket_translate_with_session(ws: WebSocket, session_id: str):
    """WebSocket 翻译端点（带指定会话 ID，用于重连）"""
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

    await handler.handle_connection(ws, session_id)
