"""多人会话与协作翻译服务（ROADMAP V5.2 落地）。

在既有「单用户实时同传」基础上补充协作能力：
- 房间（room）：一个房间对应一场同传内容，多个用户同时观看同一内容。
- 成员（member）：以会话 session_id 标识加入房间的客户端（本地回环场景下
  通常是同一台机器上的多个浏览器/桌面窗口，或同一进程内的多个会话）。
- 协作修正（collaborative revision）：房间成员可提交翻译修正，提交后
  广播给房间内所有成员 —— 类似 Google Docs 的协作编辑体验。
- 房间归属校验：只有创建者（房主）才能创建/销毁房间，其他成员只读加入。

安全约束（与项目既有 loopback 策略一致）：
- 房间 ID 使用密码学安全随机串生成（不可枚举）。
- 成员 ID 使用会话 session_id（WebSocket 已有 192bit 熵）。
- 所有 REST 端点仅允许本机回环客户端访问。
- 不持久化房间内容到磁盘（内存态，进程退出即释放）。

线程安全：FastAPI 事件循环单线程执行协程，但 REST 处理器可能被
多个 worker 并发调用，内部用锁保护共享状态。
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from loguru import logger


#: 房间最大成员数（同传场景一个房间通常 2~10 人）
MAX_ROOM_MEMBERS = 32
#: 房间保留时长（秒）：最后活跃超过该时长自动清理
ROOM_IDLE_TTL_SECONDS = 3600
#: 单房间协作修正记录上限（防长期运行内存膨胀）
MAX_REVISIONS_PER_ROOM = 500
#: 成员昵称长度上限
MAX_MEMBER_NAME_LENGTH = 32
#: 协作修正文本长度上限
MAX_REVISION_TEXT_LENGTH = 2000


class CollaborationError(Exception):
    """协作服务操作失败。"""


@dataclass
class RoomMember:
    """房间成员。

    Attributes:
        session_id: 成员会话 ID（与 WebSocket 会话 ID 一致，不可枚举）。
        name: 显示昵称。
        is_owner: 是否房主（创建者）。
        joined_at: 加入时间（epoch 秒）。
        last_seen_at: 最后活跃时间（epoch 秒）。
    """

    session_id: str
    name: str
    is_owner: bool = False
    joined_at: float = field(default_factory=time.time)
    last_seen_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "name": self.name,
            "is_owner": self.is_owner,
            "joined_at": self.joined_at,
            "last_seen_at": self.last_seen_at,
        }


@dataclass
class CollaborativeRevision:
    """协作修正记录。

    Attributes:
        room_id: 所属房间。
        revision_id: 修正记录 ID（单调递增）。
        member_session_id: 提交成员会话 ID。
        member_name: 提交成员昵称。
        segment_id: 被修正的字幕片段 ID。
        source_text: 修正后的原文（可为空表示仅修正译文）。
        new_text: 修正后的译文。
        created_at: 提交时间（epoch 秒）。
    """

    room_id: str
    revision_id: int
    member_session_id: str
    member_name: str
    segment_id: str
    source_text: str
    new_text: str
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "room_id": self.room_id,
            "revision_id": self.revision_id,
            "member_session_id": self.member_session_id,
            "member_name": self.member_name,
            "segment_id": self.segment_id,
            "source_text": self.source_text,
            "new_text": self.new_text,
            "created_at": self.created_at,
        }


@dataclass
class CollaborationRoom:
    """协作房间。

    Attributes:
        room_id: 房间 ID（密码学安全随机串）。
        owner_session_id: 房主会话 ID（创建者）。
        title: 房间标题（如「周三产品评审会议」）。
        created_at: 创建时间（epoch 秒）。
        last_active_at: 最后活跃时间（epoch 秒）。
        members: 成员列表（按加入顺序）。
        revisions: 协作修正记录（按提交顺序）。
        revision_counter: 修正记录计数器。
    """

    room_id: str
    owner_session_id: str
    title: str
    created_at: float = field(default_factory=time.time)
    last_active_at: float = field(default_factory=time.time)
    members: list[RoomMember] = field(default_factory=list)
    revisions: list[CollaborativeRevision] = field(default_factory=list)
    revision_counter: int = 0

    def to_dict(self, include_revisions: bool = True) -> dict:
        data: dict = {
            "room_id": self.room_id,
            "owner_session_id": self.owner_session_id,
            "title": self.title,
            "created_at": self.created_at,
            "last_active_at": self.last_active_at,
            "member_count": len(self.members),
            "members": [member.to_dict() for member in self.members],
        }
        if include_revisions:
            data["revision_count"] = len(self.revisions)
            data["revisions"] = [rev.to_dict() for rev in self.revisions]
        return data


class CollaborationService:
    """多人协作翻译服务：房间管理 + 协作修正广播。

    线程安全：所有共享状态通过锁保护；对外提供同步接口便于单元测试。
    """

    def __init__(self) -> None:
        self._rooms: dict[str, CollaborationRoom] = {}
        self._lock = threading.Lock()
        self._next_revision_id = 1

    @property
    def room_count(self) -> int:
        """当前房间数。"""
        with self._lock:
            return len(self._rooms)

    def create_room(self, owner_session_id: str, title: str = "") -> CollaborationRoom:
        """创建协作房间（创建者为房主）。

        Args:
            owner_session_id: 房主会话 ID。
            title: 房间标题（可为空，默认「协作翻译」）。

        Returns:
            新建的房间。

        Raises:
            CollaborationError: 参数非法。
        """
        owner_session_id = (owner_session_id or "").strip()
        title = (title or "协作翻译").strip()
        if not owner_session_id:
            raise CollaborationError("房主会话 ID 不能为空")
        if len(title) > 64:
            raise CollaborationError("房间标题过长（上限 64 字符）")

        room = CollaborationRoom(
            room_id=secrets.token_urlsafe(12),
            owner_session_id=owner_session_id,
            title=title,
        )
        room.members.append(
            RoomMember(
                session_id=owner_session_id,
                name="房主",
                is_owner=True,
            )
        )
        with self._lock:
            self._rooms[room.room_id] = room
        logger.info(
            "Collaboration room created: {} (owner {})",
            room.room_id,
            owner_session_id,
        )
        return room

    def get_room(self, room_id: str) -> Optional[CollaborationRoom]:
        """获取房间（不存在返回 None）。"""
        with self._lock:
            return self._rooms.get(room_id)

    def list_rooms(self) -> list[dict]:
        """列出所有房间（不含修正记录，供前端房间列表）。"""
        self._sweep_idle_rooms()
        with self._lock:
            return [room.to_dict(include_revisions=False) for room in self._rooms.values()]

    def join_room(self, room_id: str, session_id: str, name: str = "") -> CollaborationRoom:
        """成员加入房间（房主自动创建时已加入，幂等）。

        Args:
            room_id: 房间 ID。
            session_id: 成员会话 ID。
            name: 显示昵称（可为空，默认「成员」）。

        Returns:
            加入后的房间。

        Raises:
            CollaborationError: 房间不存在 / 成员已满 / 参数非法。
        """
        room = self.get_room(room_id)
        if room is None:
            raise CollaborationError("房间不存在")
        session_id = (session_id or "").strip()
        name = (name or "成员").strip()
        if not session_id:
            raise CollaborationError("成员会话 ID 不能为空")
        if len(name) > MAX_MEMBER_NAME_LENGTH:
            raise CollaborationError(f"昵称过长（上限 {MAX_MEMBER_NAME_LENGTH} 字符）")

        with self._lock:
            for member in room.members:
                if member.session_id == session_id:
                    member.name = name
                    member.last_seen_at = time.time()
                    room.last_active_at = time.time()
                    return room
            if len(room.members) >= MAX_ROOM_MEMBERS:
                raise CollaborationError(f"房间成员已满（上限 {MAX_ROOM_MEMBERS} 人）")
            room.members.append(
                RoomMember(
                    session_id=session_id,
                    name=name,
                )
            )
            room.last_active_at = time.time()
        logger.info(
            "Member {} joined collaboration room {} ({} members)",
            session_id,
            room_id,
            len(room.members),
        )
        return room

    def leave_room(self, room_id: str, session_id: str) -> bool:
        """成员离开房间。

        房主离开时房间销毁（同传内容由房主创建，房主离开即散场）。

        Args:
            room_id: 房间 ID。
            session_id: 成员会话 ID。

        Returns:
            是否实际离开/销毁（房间或成员不存在返回 False）。
        """
        room = self.get_room(room_id)
        if room is None:
            return False

        with self._lock:
            for index, member in enumerate(room.members):
                if member.session_id != session_id:
                    continue
                if member.is_owner:
                    self._rooms.pop(room_id, None)
                    logger.info("Collaboration room {} destroyed (owner left)", room_id)
                    return True
                del room.members[index]
                room.last_active_at = time.time()
                logger.info(
                    "Member {} left collaboration room {} ({} members)",
                    session_id,
                    room_id,
                    len(room.members),
                )
                return True
        return False

    def submit_revision(
        self,
        room_id: str,
        session_id: str,
        segment_id: str,
        new_text: str,
        source_text: str = "",
    ) -> CollaborativeRevision:
        """提交协作修正（提交后房间内全员可见）。

        Args:
            room_id: 房间 ID。
            session_id: 提交成员会话 ID（必须在房间内）。
            segment_id: 被修正的字幕片段 ID。
            new_text: 修正后的译文。
            source_text: 修正后的原文（可为空）。

        Returns:
            新增的协作修正记录。

        Raises:
            CollaborationError: 房间/成员不存在，或参数非法。
        """
        room = self.get_room(room_id)
        if room is None:
            raise CollaborationError("房间不存在")

        segment_id = (segment_id or "").strip()
        new_text = (new_text or "").strip()
        source_text = (source_text or "").strip()
        if not segment_id:
            raise CollaborationError("片段 ID 不能为空")
        if not new_text:
            raise CollaborationError("修正译文不能为空")
        if len(new_text) > MAX_REVISION_TEXT_LENGTH:
            raise CollaborationError(f"修正文本过长（上限 {MAX_REVISION_TEXT_LENGTH} 字符）")

        member_name = "成员"
        found = False
        with self._lock:
            for member in room.members:
                if member.session_id == session_id:
                    member_name = member.name
                    member.last_seen_at = time.time()
                    found = True
                    break
            if not found:
                raise CollaborationError("成员不在房间内")
            if len(room.revisions) >= MAX_REVISIONS_PER_ROOM:
                room.revisions.pop(0)
            revision = CollaborativeRevision(
                room_id=room_id,
                revision_id=self._next_revision_id,
                member_session_id=session_id,
                member_name=member_name,
                segment_id=segment_id,
                source_text=source_text,
                new_text=new_text,
            )
            self._next_revision_id += 1
            room.revisions.append(revision)
            room.last_active_at = time.time()
        logger.info(
            "Collaborative revision {} submitted by {} in room {}",
            revision.revision_id,
            session_id,
            room_id,
        )
        return revision

    def clear_revisions(self, room_id: str, session_id: str) -> int:
        """清空房间修正记录（仅房主可操作）。

        Args:
            room_id: 房间 ID。
            session_id: 操作者会话 ID（必须为房主）。

        Returns:
            清空前的修正记录数。

        Raises:
            CollaborationError: 房间不存在或非房主。
        """
        room = self.get_room(room_id)
        if room is None:
            raise CollaborationError("房间不存在")

        with self._lock:
            owner = next(
                (member for member in room.members if member.session_id == session_id),
                None,
            )
            if owner is None or not owner.is_owner:
                raise CollaborationError("仅房主可清空协作修正")
            count = len(room.revisions)
            room.revisions.clear()
            room.last_active_at = time.time()
        return count

    def destroy_room(self, room_id: str, session_id: str) -> bool:
        """销毁房间（仅房主可操作）。

        Args:
            room_id: 房间 ID。
            session_id: 操作者会话 ID（必须为房主）。

        Returns:
            是否实际销毁。

        Raises:
            CollaborationError: 房间不存在或非房主。
        """
        room = self.get_room(room_id)
        if room is None:
            raise CollaborationError("房间不存在")

        with self._lock:
            owner = next(
                (member for member in room.members if member.session_id == session_id),
                None,
            )
            if owner is None or not owner.is_owner:
                raise CollaborationError("仅房主可销毁房间")
            self._rooms.pop(room_id, None)
        logger.info("Collaboration room {} destroyed by owner {}", room_id, session_id)
        return True

    def _sweep_idle_rooms(self) -> None:
        """清理长期无活动的房间（内存保护）。"""
        now = time.time()
        with self._lock:
            idle = [
                room_id
                for room_id, room in self._rooms.items()
                if now - room.last_active_at > ROOM_IDLE_TTL_SECONDS
            ]
            for room_id in idle:
                self._rooms.pop(room_id, None)
                logger.info("Collaboration room {} swept (idle)", room_id)


#: 全局协作服务实例（在 main.py lifespan 中初始化）
_collaboration_service: Optional[CollaborationService] = None


def get_collaboration_service() -> Optional[CollaborationService]:
    """获取全局协作服务实例。"""
    return _collaboration_service


def set_collaboration_service(service: Optional[CollaborationService]) -> None:
    """设置全局协作服务实例（应用生命周期内调用）。"""
    global _collaboration_service
    _collaboration_service = service
