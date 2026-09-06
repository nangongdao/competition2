"""术语库管理服务（V5.1 落地增强）。

在既有「会话内导入术语表」基础上补齐管理能力：
- 术语库以 JSON 文件持久化到本地（默认 `config/glossary.local.json`，与
  desktop-settings 同一目录策略），重启不丢失。
- REST API 支持 list / add / delete / clear / import，供前端管理面板调用。
- 启动时加载；WebSocket 会话建立术语表时仍走 `set_glossary` 控制消息，
  前端管理面板的修改会同时写入持久化文件，并在下次翻译会话中生效。

安全约束：
- 文件路径固定为配置目录下白名单文件名，不接受用户传入路径（防路径穿越）。
- 写入使用临时文件 + 原子替换，避免写一半损坏术语库。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from threading import Lock
from typing import Optional

from loguru import logger

from services.glossary import GlossaryEntry, parse_glossary_csv, parse_glossary_json
from services.local_settings import CONFIG_DIR

#: 持久化文件名（白名单，不接受外部传入路径）
GLOSSARY_FILENAME = "glossary.local.json"
#: 单条术语源文本长度上限（防超长条目污染 prompt）
MAX_SOURCE_LENGTH = 120
#: 单条术语译文长度上限
MAX_TARGET_LENGTH = 200
#: 术语库条目数上限
MAX_GLOSSARY_ENTRIES = 2000

#: 条目标识符：仅允许安全字符（用于 id 校验，防注入）
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class GlossaryError(Exception):
    """术语库操作失败。"""


class GlossaryManager:
    """术语库管理：内存索引 + 本地 JSON 持久化。

    线程安全：REST 处理器可能并发调用，内部用锁保护共享状态。
    """

    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            path = CONFIG_DIR / GLOSSARY_FILENAME
        self._path = Path(path)
        self._entries: list[GlossaryEntry] = []
        self._lock = Lock()
        self._load()

    @property
    def path(self) -> Path:
        """持久化文件路径。"""
        return self._path

    @property
    def size(self) -> int:
        """当前术语条数。"""
        with self._lock:
            return len(self._entries)

    @property
    def entries(self) -> list[GlossaryEntry]:
        """返回条目副本（快照）。"""
        with self._lock:
            return list(self._entries)

    def to_dict(self) -> dict:
        """转换为可 JSON 序列化的字典（供 REST 返回）。"""
        return {
            "path": str(self._path),
            "size": self.size,
            "entries": [
                {
                    "id": self._entry_id(entry),
                    "source": entry.source,
                    "target": entry.target,
                    "keep_original": entry.keep_original,
                }
                for entry in self.entries
            ],
        }

    def list_entries(self) -> list[dict]:
        """返回条目列表（REST list）。"""
        return self.to_dict()["entries"]

    def add_entry(self, source: str, target: str, keep_original: bool = False) -> dict:
        """新增术语条目。

        Args:
            source: 术语原文。
            target: 译文（keep_original=True 时可为空）。
            keep_original: 是否强制保持原文不翻译。

        Returns:
            新增条目（含 id）。

        Raises:
            GlossaryError: 参数非法或条目已存在。
        """
        source = (source or "").strip()
        target = (target or "").strip()
        if not source:
            raise GlossaryError("术语原文不能为空")
        if len(source) > MAX_SOURCE_LENGTH:
            raise GlossaryError(f"术语原文过长（上限 {MAX_SOURCE_LENGTH} 字符）")
        if len(target) > MAX_TARGET_LENGTH:
            raise GlossaryError(f"术语译文过长（上限 {MAX_TARGET_LENGTH} 字符）")

        entry = GlossaryEntry(
            source=source,
            target=target,
            keep_original=bool(keep_original),
        )

        with self._lock:
            if len(self._entries) >= MAX_GLOSSARY_ENTRIES:
                raise GlossaryError(f"术语库已满（上限 {MAX_GLOSSARY_ENTRIES} 条）")
            for existing in self._entries:
                if existing.source.lower() == source.lower():
                    raise GlossaryError(f"术语「{source}」已存在")
            self._entries.append(entry)
            self._persist_locked()

        return {
            "id": self._entry_id(entry),
            "source": entry.source,
            "target": entry.target,
            "keep_original": entry.keep_original,
        }

    def delete_entry(self, entry_id: str) -> bool:
        """删除指定术语条目。

        Args:
            entry_id: 条目 id（source 的规范化形式）。

        Returns:
            是否实际删除（不存在返回 False）。
        """
        if not _SAFE_ID_RE.fullmatch(entry_id):
            return False
        with self._lock:
            for index, entry in enumerate(self._entries):
                if self._entry_id(entry) == entry_id:
                    del self._entries[index]
                    self._persist_locked()
                    return True
        return False

    def clear(self) -> int:
        """清空全部术语。

        Returns:
            清空前的条目数。
        """
        with self._lock:
            count = len(self._entries)
            if count == 0:
                return 0
            self._entries.clear()
            self._persist_locked()
        return count

    def import_entries(self, raw: object) -> int:
        """从 JSON/CSV 解析结果导入术语表（追加合并）。

        Args:
            raw: parse_glossary_json / parse_glossary_csv 接受的原始输入。

        Returns:
            实际新增的条目数（已存在的跳过）。
        """
        parsed = self._normalize_parsed(raw)
        if not parsed:
            return 0

        imported = 0
        with self._lock:
            for entry in parsed:
                if len(self._entries) >= MAX_GLOSSARY_ENTRIES:
                    break
                exists = any(
                    existing.source.lower() == entry.source.lower()
                    for existing in self._entries
                )
                if exists:
                    continue
                self._entries.append(entry)
                imported += 1
            if imported:
                self._persist_locked()
        return imported

    def replace_all(self, entries: list[GlossaryEntry]) -> int:
        """整体替换术语库（用于会话启动时同步管理面板内容）。

        Args:
            entries: 完整术语表条目。

        Returns:
            替换后的条目数。
        """
        with self._lock:
            self._entries = list(entries)[:MAX_GLOSSARY_ENTRIES]
            self._persist_locked()
        return len(self._entries)

    def as_glossary_entries(self) -> list[GlossaryEntry]:
        """返回内部条目（供 WebSocket set_glossary 复用）。"""
        return self.entries

    @staticmethod
    def _entry_id(entry: GlossaryEntry) -> str:
        """生成条目稳定 id：源文本规范化（小写、去除空白标点）。"""
        normalized = re.sub(r"[\s，。！？；：、,.;:!?()\[\]{}]+", "-", entry.source.lower())
        normalized = re.sub(r"-+", "-", normalized).strip("-")
        return normalized[:64] or "entry"

    def _normalize_parsed(self, raw: object) -> list[GlossaryEntry]:
        """统一处理 JSON/CSV 两种解析输入。"""
        if isinstance(raw, str):
            return parse_glossary_csv(raw)
        return parse_glossary_json(raw)

    def _load(self) -> None:
        """从磁盘加载术语库（文件不存在或损坏时静默降级为空库）。"""
        try:
            if not self._path.exists():
                logger.info("Glossary file not found, starting empty: {}", self._path)
                return
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            candidates = raw.get("entries", []) if isinstance(raw, dict) else raw
            entries = parse_glossary_json(candidates)
            self._entries = entries[:MAX_GLOSSARY_ENTRIES]
            logger.info("Glossary loaded: {} entries from {}", len(self._entries), self._path)
        except Exception as exc:
            logger.error("Failed to load glossary file {}: {}", self._path, exc)
            self._entries = []

    def _persist_locked(self) -> None:
        """原子写回磁盘（调用方必须持有锁）。"""
        payload = {
            "version": 1,
            "entries": [
                {
                    "source": entry.source,
                    "target": entry.target,
                    "keep_original": entry.keep_original,
                }
                for entry in self._entries
            ],
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._path.with_suffix(".json.tmp")
            tmp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp_path.replace(self._path)
        except Exception as exc:
            logger.error("Failed to persist glossary {}: {}", self._path, exc)
            raise GlossaryError(f"术语库写入失败: {exc}") from exc


#: 全局术语库管理实例（在 main.py lifespan 中初始化）
_glossary_manager: Optional[GlossaryManager] = None


def get_glossary_manager() -> Optional[GlossaryManager]:
    """获取全局术语库管理实例。"""
    return _glossary_manager


def set_glossary_manager(manager: Optional[GlossaryManager]) -> None:
    """设置全局术语库管理实例（应用生命周期内调用）。"""
    global _glossary_manager
    _glossary_manager = manager
