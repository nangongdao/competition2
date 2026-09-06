"""Session data lifecycle & privacy control (ROADMAP Phase 10).

会话数据生命周期管理：
- 记录每个会话的开始时间、句数、时长（本地 JSON 持久化，零依赖）
- 支持按会话删除 / 清空全部（隐私控制）
- TTL 自动清理过期会话记录（数据生命周期）

与 Redis 中的实时上下文（ContextManager）解耦：本服务只维护
会话元数据台账，不触碰实时翻译数据，清理安全、可回退。
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Optional

from loguru import logger

from core.config import REPO_ROOT


#: 会话台账默认存储位置（Git 忽略）。
DEFAULT_SESSION_LOG_PATH = REPO_ROOT / "config" / "session-history.local.json"


class SessionDataService:
    """维护本地会话历史台账（生命周期 + 隐私控制）。"""

    #: 默认保留时长（秒）：7 天。
    DEFAULT_RETENTION_SECONDS = 7 * 24 * 3600

    def __init__(
        self,
        *,
        storage_path: Path | None = None,
        retention_seconds: int | None = None,
    ) -> None:
        self._storage_path = storage_path or DEFAULT_SESSION_LOG_PATH
        self._retention_seconds = (
            retention_seconds
            if retention_seconds is not None
            else self.DEFAULT_RETENTION_SECONDS
        )
        self._lock = threading.Lock()
        self._sessions: dict[str, dict] = {}
        self._load()

    # ---- 台账读写 ----

    def _load(self) -> None:
        """从磁盘加载会话台账；文件缺失/损坏时安全降级为空台账。"""
        try:
            if not self._storage_path.exists():
                return
            raw = json.loads(self._storage_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self._sessions = raw
        except Exception as exc:
            logger.warning(
                "Failed to load session history from {}: {}",
                self._storage_path,
                exc,
            )
            self._sessions = {}

    def _persist(self) -> None:
        """原子写入台账（先写临时文件再替换，防半写损坏）。"""
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._storage_path.with_suffix(".tmp")
            tmp_path.write_text(
                json.dumps(self._sessions, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp_path.replace(self._storage_path)
        except Exception as exc:
            logger.error("Failed to persist session history: {}", exc)

    # ---- 记录与查询 ----

    def record_session_start(self, session_id: str) -> None:
        """记录一个会话的开始。

        Args:
            session_id: 会话 ID。
        """
        if not session_id or not isinstance(session_id, str):
            return
        with self._lock:
            now = time.time()
            existing = self._sessions.get(session_id)
            if existing:
                existing["updated_at"] = now
            else:
                self._sessions[session_id] = {
                    "session_id": session_id,
                    "started_at": now,
                    "updated_at": now,
                    "segment_count": 0,
                    "duration_ms": 0,
                    # 阶段 10 可观测性补全：质量指标随会话落盘
                    "quality": self._empty_quality(),
                }
            self._persist()

    def update_session_progress(
        self,
        session_id: str,
        *,
        segment_count: int | None = None,
        duration_ms: int | None = None,
    ) -> None:
        """更新会话进度（句数 / 时长）。

        Args:
            session_id: 会话 ID。
            segment_count: 累计句数（可为 None 表示不更新）。
            duration_ms: 会话时长（毫秒，可为 None 表示不更新）。
        """
        if not session_id or not isinstance(session_id, str):
            return
        with self._lock:
            record = self._sessions.get(session_id)
            if record is None:
                return
            if segment_count is not None:
                record["segment_count"] = max(0, int(segment_count))
            if duration_ms is not None:
                record["duration_ms"] = max(0, int(duration_ms))
            record["updated_at"] = time.time()
            self._persist()

    def update_session_quality(self, session_id: str, quality: dict) -> None:
        """写入会话质量指标（阶段 10 可观测性补全）。

        由 Pipeline 停止时把诊断快照中的质量维度持久化到会话台账，
        供历史面板回看每次观看的质量表现（延迟/丢包/修正等）。

        Args:
            session_id: 会话 ID。
            quality: 质量指标字典（需可 JSON 序列化）。
        """
        if not session_id or not isinstance(session_id, str):
            return
        if not isinstance(quality, dict):
            return
        with self._lock:
            record = self._sessions.get(session_id)
            if record is None:
                return
            record["quality"] = {
                **self._empty_quality(),
                **{k: v for k, v in quality.items() if v is not None},
            }
            record["updated_at"] = time.time()
            self._persist()

    @staticmethod
    def _empty_quality() -> dict:
        """空质量指标模板（保证字段一致）。"""
        return {
            "asr_segments": 0,
            "translation_segments": 0,
            "revision_segments": 0,
            "audio_chunks_received": 0,
            "audio_chunks_dropped": 0,
            "audio_queue_max_depth": 0,
            "audio_queue_capacity": 0,
            "reconnect_count": 0,
            "latency": {},
            "api_call_counts": {},
        }

    def list_sessions(self, *, limit: int = 100) -> list[dict]:
        """返回会话台账列表（按开始时间倒序）。

        Args:
            limit: 最多返回条数。

        Returns:
            会话记录列表（dict 拷贝，避免外部修改内部状态）。
        """
        with self._lock:
            sessions = [
                {**record}
                for record in self._sessions.values()
            ]
        sessions.sort(key=lambda item: item.get("started_at", 0), reverse=True)
        return sessions[: max(1, limit)]

    def delete_session(self, session_id: str) -> bool:
        """删除指定会话记录（隐私控制）。

        Args:
            session_id: 会话 ID。

        Returns:
            是否确实删除了记录。
        """
        if not session_id or not isinstance(session_id, str):
            return False
        with self._lock:
            existed = self._sessions.pop(session_id, None) is not None
            if existed:
                self._persist()
        return existed

    def clear_all(self) -> int:
        """清空全部会话记录（隐私控制）。

        Returns:
            清空的记录数。
        """
        with self._lock:
            count = len(self._sessions)
            self._sessions.clear()
            if count:
                self._persist()
        return count

    def purge_expired(self) -> int:
        """清理超过保留期的过期会话记录（数据生命周期）。

        Returns:
            清理的记录数。
        """
        now = time.time()
        deadline = now - self._retention_seconds
        expired: list[str] = []
        with self._lock:
            for session_id, record in self._sessions.items():
                started_at = record.get("started_at", 0)
                if isinstance(started_at, (int, float)) and started_at < deadline:
                    expired.append(session_id)
            for session_id in expired:
                self._sessions.pop(session_id, None)
            if expired:
                self._persist()
        return len(expired)

    def stats(self) -> dict:
        """台账统计（供 REST 端点展示）。"""
        with self._lock:
            total = len(self._sessions)
            total_segments = sum(
                int(record.get("segment_count", 0))
                for record in self._sessions.values()
            )
        return {
            "total_sessions": total,
            "total_segments": total_segments,
            "retention_seconds": self._retention_seconds,
        }

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._sessions)


#: 全局单例（应用生命周期内复用，类似 glossary/subscription 服务）。
_service: Optional[SessionDataService] = None
_service_lock = threading.Lock()


def get_session_data_service() -> SessionDataService | None:
    """返回全局会话台账服务实例（未初始化时为 None）。"""
    return _service


def set_session_data_service(service: SessionDataService | None) -> None:
    """注入全局会话台账服务实例（应用启动时调用）。"""
    global _service
    _service = service
