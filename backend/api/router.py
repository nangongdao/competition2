"""FastAPI 路由定义"""

import asyncio
import secrets
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from loguru import logger
from pydantic import BaseModel, ConfigDict

from api.websocket_handler import WebSocketHandler
from core.config import settings
from services.collaboration import (
    CollaborationError,
    get_collaboration_service,
)
from services.cost_service import get_cost_service
from services.glossary_manager import (
    GlossaryError,
    get_glossary_manager,
)
from services.local_settings import (
    create_settings_snapshot,
    read_local_settings,
    save_local_settings_update,
)
from services.session_summary import SessionSummaryService
from services.session_data_service import get_session_data_service
from services.subscription import (
    PLANS,
    SubscriptionError,
    get_subscription_service,
)
from services.terminal_bridge import TerminalBridge

# 全局终端桥接（在 main.py 中初始化）
_terminal_bridge: TerminalBridge | None = None


def set_terminal_bridge(bridge: TerminalBridge) -> None:
    """设置全局终端桥接实例（应用生命周期内调用一次）。"""
    global _terminal_bridge
    _terminal_bridge = bridge


def get_terminal_bridge() -> TerminalBridge | None:
    """获取全局终端桥接实例。"""
    return _terminal_bridge

router = APIRouter()
LOOPBACK_CLIENT_HOSTS = {"127.0.0.1", "::1", "localhost"}

# 全局 WebSocket 处理器（在 main.py 中初始化）
_ws_handler: WebSocketHandler | None = None

# 全局会话摘要服务（在 main.py 中初始化，NMT 客户端复用 WebSocket 处理器实例）
_summary_service: SessionSummaryService | None = None


def set_summary_service(service: SessionSummaryService | None) -> None:
    """设置全局会话摘要服务实例。"""
    global _summary_service
    _summary_service = service


def get_summary_service() -> SessionSummaryService | None:
    """获取全局会话摘要服务实例。"""
    return _summary_service


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
    targetLanguage: str | None = None


class LocalSubtitleStyleSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    fontSize: int | None = None
    fontColor: str | None = None
    backgroundColor: str | None = None
    backgroundOpacity: float | None = None
    position: str | None = None


class LocalSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    uiLanguage: str | None = None
    translation: LocalTranslationSettingsUpdate | None = None
    asr: LocalAsrSettingsUpdate | None = None
    runtime: LocalRuntimeSettingsUpdate | None = None
    subtitleStyle: LocalSubtitleStyleSettingsUpdate | None = None


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


@router.get("/tts/stats")
async def get_tts_stats(request: Request):
    """获取后端 TTS 合成与缓存统计（仅本机回环客户端）。"""
    require_loopback_client(request)
    handler = get_ws_handler()
    if handler is None:
        return {"success": True, "stats": {"enabled": False, "engine": "off", "active": 0}}
    return {"success": True, "stats": handler.get_tts_stats()}


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


@router.get("/sessions/{session_id}/summary")
async def get_session_summary(session_id: str, request: Request, use_llm: bool = False):
    """获取会话学习摘要（ROADMAP 阶段 9 / AC-G7）。

    默认返回本地统计摘要（关键词 / 时长 / 修正数等，零成本离线可用）；
    `?use_llm=true` 时尝试 LLM 增强摘要（要点 + 行动项），失败自动降级为本地摘要。
    仅允许本机回环客户端访问，避免跨站读取会话内容。
    """
    require_loopback_client(request)

    handler = get_ws_handler()
    summary_service = get_summary_service()
    if handler is None or summary_service is None:
        return {
            "success": False,
            "reason": "summary service is not initialized",
        }

    try:
        window = await handler.get_session_window(session_id)
    except Exception as exc:
        logger.warning("Failed to load session window for summary {}: {}", session_id, exc)
        return {
            "success": False,
            "reason": "failed to load session context",
        }

    if window is None:
        return {
            "success": True,
            "reason": "session not found or already expired",
            "summary": None,
        }

    summary = await summary_service.build_summary(
        session_id,
        window,
        use_llm=use_llm,
    )
    return {
        "success": True,
        "reason": "session summary generated",
        "summary": summary.to_dict(),
    }


class GlossaryAddRequest(BaseModel):
    """新增术语条目请求体。"""

    model_config = ConfigDict(extra="ignore")

    source: str
    target: str = ""
    keep_original: bool = False


class GlossaryImportRequest(BaseModel):
    """术语库导入请求体。

    支持两种内容：
    - ``entries``：结构化 JSON 列表（[{source, target, keep_original}]）
    - ``csv``：CSV 文本（source,target[,keep_original]）
    """

    model_config = ConfigDict(extra="ignore")

    entries: list[dict] | None = None
    csv: str | None = None


@router.get("/glossary")
async def get_glossary(request: Request):
    """获取术语库（ROADMAP V5.1 管理增强）。

    仅允许本机回环客户端访问。
    """
    require_loopback_client(request)
    manager = get_glossary_manager()
    if manager is None:
        return {"success": False, "reason": "glossary service is not initialized"}
    return {
        "success": True,
        "reason": "glossary loaded",
        "glossary": manager.to_dict(),
    }


@router.post("/glossary")
async def add_glossary_entry(request: Request, body: GlossaryAddRequest):
    """新增术语条目。"""
    require_loopback_client(request)
    manager = get_glossary_manager()
    if manager is None:
        return {"success": False, "reason": "glossary service is not initialized"}
    try:
        entry = manager.add_entry(
            body.source,
            body.target,
            keep_original=body.keep_original,
        )
    except GlossaryError as exc:
        return {"success": False, "reason": str(exc)}
    return {"success": True, "reason": "glossary entry added", "entry": entry}


@router.delete("/glossary/{entry_id}")
async def delete_glossary_entry(entry_id: str, request: Request):
    """删除术语条目。"""
    require_loopback_client(request)
    manager = get_glossary_manager()
    if manager is None:
        return {"success": False, "reason": "glossary service is not initialized"}
    deleted = manager.delete_entry(entry_id)
    return {
        "success": deleted,
        "reason": "glossary entry deleted" if deleted else "glossary entry not found",
    }


@router.delete("/glossary")
async def clear_glossary(request: Request):
    """清空术语库。"""
    require_loopback_client(request)
    manager = get_glossary_manager()
    if manager is None:
        return {"success": False, "reason": "glossary service is not initialized"}
    count = manager.clear()
    return {"success": True, "reason": f"cleared {count} glossary entries", "cleared": count}


@router.post("/glossary/import")
async def import_glossary(request: Request, body: GlossaryImportRequest):
    """导入术语表（JSON 数组 / CSV 文本）。"""
    require_loopback_client(request)
    manager = get_glossary_manager()
    if manager is None:
        return {"success": False, "reason": "glossary service is not initialized"}

    if body.csv is not None:
        raw: object = body.csv
    elif body.entries is not None:
        raw = body.entries
    else:
        return {"success": False, "reason": "provide either entries or csv"}

    imported = manager.import_entries(raw)
    return {
        "success": True,
        "reason": f"imported {imported} glossary entries",
        "imported": imported,
        "glossary": manager.to_dict(),
    }


@router.get("/translation-memory")
async def get_translation_memory_stats(request: Request):
    """获取翻译记忆库统计（ROADMAP V5.3）。

    只读统计端点：聚合活跃会话记忆库统计 + 跨会话持久化存储统计。
    仅允许本机回环客户端访问。
    """
    require_loopback_client(request)
    handler = get_ws_handler()
    if handler is None:
        return {"success": False, "reason": "translation service is not initialized"}
    stats = handler.translation_memory_summary()

    # V5.3 生产化：附带跨会话持久化存储统计（跨会话累积句对）
    from services.translation_memory_store import get_tm_store

    store = get_tm_store()
    store_stats: dict[str, object] = {
        "persisted": False,
        "size": 0,
        "pairs": 0,
        "by_pair": {},
    }
    if store is not None:
        store_stats = {
            "persisted": True,
            **store.stats(),
        }
    stats["store"] = store_stats
    return {
        "success": True,
        "reason": "translation memory stats",
        "stats": stats,
    }


@router.post("/translation-memory/clear")
async def clear_translation_memory(request: Request):
    """清空翻译记忆库（活跃会话记忆库 + 跨会话持久化存储）。

    仅允许本机回环客户端访问。
    """
    require_loopback_client(request)
    handler = get_ws_handler()
    if handler is None:
        return {"success": False, "reason": "translation service is not initialized"}
    cleared = handler.clear_translation_memory()

    from services.translation_memory_store import get_tm_store

    store_cleared = 0
    store = get_tm_store()
    if store is not None:
        store_cleared = store.clear_all()
    return {
        "success": True,
        "reason": (
            f"cleared translation memory of {cleared} active session(s) "
            f"and {store_cleared} persisted pair(s)"
        ),
        "cleared": cleared,
        "store_cleared": store_cleared,
    }


@router.get("/translation-memory/entries")
async def get_translation_memory_entries(request: Request):
    """获取跨会话持久化翻译记忆库句对列表（V5.3 生产化）。

    仅允许本机回环客户端访问。
    """
    require_loopback_client(request)
    from services.translation_memory_store import get_tm_store

    store = get_tm_store()
    if store is None:
        return {"success": False, "reason": "translation memory store is not initialized"}
    language_pair = request.query_params.get("language_pair", "")
    entries = (
        store.pair_entries(language_pair)
        if language_pair
        else store.all_entries(limit=200)
    )
    return {
        "success": True,
        "reason": "translation memory entries",
        "size": len(entries),
        "entries": entries,
    }


class CollaborationCreateRequest(BaseModel):
    """创建协作房间请求体（V5.2）。"""

    model_config = ConfigDict(extra="ignore")

    ownerSessionId: str
    title: str = "协作翻译"


class CollaborationJoinRequest(BaseModel):
    """加入协作房间请求体（V5.2）。"""

    model_config = ConfigDict(extra="ignore")

    sessionId: str
    name: str = "成员"


class CollaborationRevisionRequest(BaseModel):
    """提交协作修正请求体（V5.2）。"""

    model_config = ConfigDict(extra="ignore")

    sessionId: str
    segmentId: str
    newText: str
    sourceText: str = ""


class SubscriptionUpdateRequest(BaseModel):
    """切换套餐请求体（V5.5）。"""

    model_config = ConfigDict(extra="ignore")

    plan: str


@router.get("/collaboration/rooms")
async def list_collaboration_rooms(request: Request):
    """列出协作房间（ROADMAP V5.2 多人会话与协作翻译）。

    仅允许本机回环客户端访问。
    """
    require_loopback_client(request)
    service = get_collaboration_service()
    if service is None:
        return {"success": False, "reason": "collaboration service is not initialized"}
    return {
        "success": True,
        "reason": "collaboration rooms listed",
        "rooms": service.list_rooms(),
    }


@router.post("/collaboration/rooms")
async def create_collaboration_room(request: Request, body: CollaborationCreateRequest):
    """创建协作房间（V5.2）。

    创建者为房主，自动加入房间。
    """
    require_loopback_client(request)
    service = get_collaboration_service()
    if service is None:
        return {"success": False, "reason": "collaboration service is not initialized"}
    try:
        room = service.create_room(body.ownerSessionId, body.title)
    except CollaborationError as exc:
        return {"success": False, "reason": str(exc)}
    return {"success": True, "reason": "collaboration room created", "room": room.to_dict()}


@router.get("/collaboration/rooms/{room_id}")
async def get_collaboration_room(room_id: str, request: Request):
    """获取协作房间详情（含成员与协作修正记录，V5.2）。"""
    require_loopback_client(request)
    service = get_collaboration_service()
    if service is None:
        return {"success": False, "reason": "collaboration service is not initialized"}
    room = service.get_room(room_id)
    if room is None:
        return {"success": False, "reason": "collaboration room not found"}
    return {"success": True, "reason": "collaboration room loaded", "room": room.to_dict()}


@router.post("/collaboration/rooms/{room_id}/join")
async def join_collaboration_room(room_id: str, request: Request, body: CollaborationJoinRequest):
    """加入协作房间（V5.2）。"""
    require_loopback_client(request)
    service = get_collaboration_service()
    if service is None:
        return {"success": False, "reason": "collaboration service is not initialized"}
    try:
        room = service.join_room(room_id, body.sessionId, body.name)
    except CollaborationError as exc:
        return {"success": False, "reason": str(exc)}
    return {"success": True, "reason": "joined collaboration room", "room": room.to_dict()}


@router.post("/collaboration/rooms/{room_id}/leave")
async def leave_collaboration_room(room_id: str, request: Request, body: CollaborationJoinRequest):
    """离开协作房间（V5.2）。

    房主离开时房间销毁。
    """
    require_loopback_client(request)
    service = get_collaboration_service()
    if service is None:
        return {"success": False, "reason": "collaboration service is not initialized"}
    left = service.leave_room(room_id, body.sessionId)
    return {"success": left, "reason": "left collaboration room" if left else "not in room"}


@router.post("/collaboration/rooms/{room_id}/revisions")
async def submit_collaboration_revision(
    room_id: str,
    request: Request,
    body: CollaborationRevisionRequest,
):
    """提交协作修正（V5.2，提交后房间内全员可见）。"""
    require_loopback_client(request)
    service = get_collaboration_service()
    if service is None:
        return {"success": False, "reason": "collaboration service is not initialized"}
    try:
        revision = service.submit_revision(
            room_id,
            body.sessionId,
            body.segmentId,
            body.newText,
            source_text=body.sourceText,
        )
    except CollaborationError as exc:
        return {"success": False, "reason": str(exc)}
    return {"success": True, "reason": "collaborative revision submitted", "revision": revision.to_dict()}


@router.delete("/collaboration/rooms/{room_id}/revisions")
async def clear_collaboration_revisions(room_id: str, request: Request, sessionId: str = ""):
    """清空协作修正记录（仅房主，V5.2）。"""
    require_loopback_client(request)
    service = get_collaboration_service()
    if service is None:
        return {"success": False, "reason": "collaboration service is not initialized"}
    try:
        count = service.clear_revisions(room_id, sessionId)
    except CollaborationError as exc:
        return {"success": False, "reason": str(exc)}
    return {"success": True, "reason": f"cleared {count} collaborative revisions", "cleared": count}


@router.delete("/collaboration/rooms/{room_id}")
async def destroy_collaboration_room(room_id: str, request: Request, sessionId: str = ""):
    """销毁协作房间（仅房主，V5.2）。"""
    require_loopback_client(request)
    service = get_collaboration_service()
    if service is None:
        return {"success": False, "reason": "collaboration service is not initialized"}
    try:
        destroyed = service.destroy_room(room_id, sessionId)
    except CollaborationError as exc:
        return {"success": False, "reason": str(exc)}
    return {"success": True, "reason": "collaboration room destroyed" if destroyed else "room not found"}


@router.get("/subscription")
async def get_subscription(request: Request):
    """获取订阅状态与配额（ROADMAP V5.5 付费与订阅）。

    返回当前套餐、每日已用/剩余句数、套餐能力清单。
    仅允许本机回环客户端访问。
    """
    require_loopback_client(request)
    service = get_subscription_service()
    if service is None:
        return {"success": False, "reason": "subscription service is not initialized"}
    return {
        "success": True,
        "reason": "subscription loaded",
        "subscription": service.snapshot(),
        "plans": [
            {
                "key": key,
                "name": plan["name"],
                "name_en": plan["name_en"],
                "price": plan["price"],
                "daily_limit": plan["daily_limit"],
                "features": plan["features"],
            }
            for key, plan in PLANS.items()
        ],
    }


@router.put("/subscription")
async def update_subscription(request: Request, body: SubscriptionUpdateRequest):
    """切换套餐（V5.5，本地演示/评审用）。"""
    require_loopback_client(request)
    service = get_subscription_service()
    if service is None:
        return {"success": False, "reason": "subscription service is not initialized"}
    try:
        subscription = service.set_plan(body.plan)
    except SubscriptionError as exc:
        return {"success": False, "reason": str(exc)}
    return {"success": True, "reason": "subscription plan updated", "subscription": subscription}


@router.post("/subscription/reset")
async def reset_subscription_usage(request: Request):
    """重置当天配额用量（V5.5，管理/测试用）。"""
    require_loopback_client(request)
    service = get_subscription_service()
    if service is None:
        return {"success": False, "reason": "subscription service is not initialized"}
    subscription = service.reset_daily_usage()
    return {"success": True, "reason": "daily usage reset", "subscription": subscription}


@router.get("/cost")
async def get_cost_overview(request: Request):
    """获取商用成本概览（用量计量 + 成本估算 + 熔断建议）。

    返回累计/当日用量（NMT token、ASR 秒数、TTS 字符数）、估算成本
    （美元 + 人民币）与降级建议。仅允许本机回环客户端访问。
    """
    require_loopback_client(request)
    service = get_cost_service()
    if service is None:
        return {"success": False, "reason": "cost service is not initialized"}
    return service.snapshot()


@router.post("/cost/reset")
async def reset_cost_usage(request: Request):
    """清空成本累计用量（管理/测试用）。"""
    require_loopback_client(request)
    service = get_cost_service()
    if service is None:
        return {"success": False, "reason": "cost service is not initialized"}
    return service.reset()


@router.get("/session-history")
async def list_session_history(request: Request, limit: int = 100):
    """获取会话历史台账（阶段 10 数据生命周期）。

    返回按开始时间倒序的会话记录（session_id / 开始时间 / 句数 / 时长），
    供前端展示与隐私管理。仅允许本机回环客户端访问。
    """
    require_loopback_client(request)
    service = get_session_data_service()
    if service is None:
        return {"success": False, "reason": "session data service is not initialized"}
    return {
        "success": True,
        "reason": "session history loaded",
        "sessions": service.list_sessions(limit=limit),
        "stats": service.stats(),
    }


@router.delete("/session-history/{session_id}")
async def delete_session_history(session_id: str, request: Request):
    """删除指定会话记录（阶段 10 隐私控制）。"""
    require_loopback_client(request)
    service = get_session_data_service()
    if service is None:
        return {"success": False, "reason": "session data service is not initialized"}
    deleted = service.delete_session(session_id)
    return {
        "success": deleted,
        "reason": "session history deleted" if deleted else "session history not found",
    }


@router.delete("/session-history")
async def clear_session_history(request: Request):
    """清空全部会话记录（阶段 10 隐私控制）。"""
    require_loopback_client(request)
    service = get_session_data_service()
    if service is None:
        return {"success": False, "reason": "session data service is not initialized"}
    count = service.clear_all()
    return {"success": True, "reason": f"cleared {count} session records", "cleared": count}


@router.post("/session-history/purge")
async def purge_session_history(request: Request):
    """手动触发过期会话清理（阶段 10 数据生命周期）。"""
    require_loopback_client(request)
    service = get_session_data_service()
    if service is None:
        return {"success": False, "reason": "session data service is not initialized"}
    purged = service.purge_expired()
    return {"success": True, "reason": f"purged {purged} expired sessions", "purged": purged}



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


@router.websocket("/ws/terminal")
async def websocket_terminal(ws: WebSocket):
    """内置终端 WebSocket 端点。

    前端 xterm.js 通过此端点连接，服务端派生 PTY 子进程并桥接输入输出。
    仅允许本地回环来源（Origin 校验由 _is_allowed_ws_origin 完成）。
    """
    if not _is_allowed_ws_origin(ws.headers.get("origin")):
        logger.warning("Rejected terminal websocket from origin {}", ws.headers.get("origin"))
        await _reject_unauthorized_ws(ws)
        return

    bridge = get_terminal_bridge()
    if bridge is None:
        await ws.accept()
        await ws.send_json({
            "type": "error",
            "code": "SERVICE_NOT_READY",
            "message": "Terminal service is not initialized",
        })
        await ws.close()
        return

    await ws.accept()

    # 密码学安全的随机会话 ID，避免被枚举
    session_id = secrets.token_urlsafe(24)
    try:
        session = bridge.create_session(session_id)
        session.start()
    except Exception as exc:
        logger.error("Failed to start terminal session: {}", exc)
        await ws.send_json({
            "type": "error",
            "code": "TERMINAL_START_FAILED",
            "message": str(exc),
        })
        await ws.close()
        return

    async def send_output(frame: bytes) -> None:
        await ws.send_bytes(frame)

    reader_task = None
    try:
        reader_task = asyncio.create_task(session.run(send_output))
        while True:
            raw = await ws.receive()
            if raw["type"] == "websocket.disconnect":
                break
            if raw["type"] != "websocket.receive":
                continue

            if "bytes" in raw:
                session.write_input(raw["bytes"])
                continue

            if "text" in raw:
                await _handle_terminal_control(session, raw["text"])
    except WebSocketDisconnect:
        logger.info("Terminal WebSocket disconnected: {}", session_id)
    except Exception as exc:
        logger.error("Terminal WebSocket error for {}: {}", session_id, exc)
    finally:
        if reader_task is not None:
            reader_task.cancel()
        bridge.remove_session(session_id)


async def _handle_terminal_control(session, text: str) -> None:
    """处理终端控制消息（JSON）。"""
    try:
        import json

        msg = json.loads(text)
    except json.JSONDecodeError:
        return

    msg_type = msg.get("type")
    if msg_type == "resize":
        cols = msg.get("cols")
        rows = msg.get("rows")
        if isinstance(cols, (int, float)) and isinstance(rows, (int, float)):
            session.resize(int(cols), int(rows))
    elif msg_type == "ping":
        return
    else:
        logger.debug("Unknown terminal control message: {}", msg_type)
