"""FastAPI 路由定义"""

import uuid

from fastapi import APIRouter, WebSocket
from loguru import logger

from api.websocket_handler import WebSocketHandler

router = APIRouter()

# 全局 WebSocket 处理器（在 main.py 中初始化）
_ws_handler: WebSocketHandler | None = None


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