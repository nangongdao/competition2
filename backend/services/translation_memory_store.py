"""翻译记忆库持久化存储（V5.3 生产化补全）。

会话级翻译记忆库（TranslationMemoryService）在会话结束即释放，无法跨场累积
「翻过的句子越用越准、越用越省」的记忆。本模块提供跨会话共享的持久化层：

- 句对按语言对分组存储到本地 JSON（`config/translation-memory.local.json`），
  重启不丢失、跨会话累积。
- 线程安全（REST 端点与 Pipeline 可能并发访问），写入使用临时文件 + 原子替换。
- 容量上限保护，防超长会话/海量数据膨胀磁盘与内存。

设计约束（与 ROADMAP V5.3 对齐）：
- 不引入向量数据库等重依赖，纯标准库 JSON 持久化。
- 与术语库管理（glossary_manager.py）、会话台账（session_data_service.py）
  保持一致的「内存索引 + 原子落盘」模式。
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Optional

from loguru import logger

from core.config import REPO_ROOT

#: 默认持久化文件名（Git 忽略；白名单文件名，不接受外部传入路径）。
DEFAULT_TM_STORE_PATH = REPO_ROOT / "config" / "translation-memory.local.json"
#: 全部语言对共享的最大句对总数（跨会话累积上限）。
MAX_STORE_ENTRIES = 5000
#: 单次写入的最大条目数（防极端场景单次落盘过大）。
MAX_BATCH_ENTRIES = 500


class TranslationMemoryStore:
    """跨会话翻译记忆库持久化存储。

    结构：``{"version": 1, "entries": [{"source", "translated",
    "language_pair", "created_at"}, ...]}``

    线程安全：所有读写经 ``self._lock`` 串行化；``lookup``/``all_entries``
    返回副本，避免外部修改内部状态。
    """

    def __init__(self, path: Path | None = None, *, max_entries: int = MAX_STORE_ENTRIES) -> None:
        self._path = Path(path) if path is not None else DEFAULT_TM_STORE_PATH
        self._max_entries = max(1, int(max_entries))
        self._lock = threading.Lock()
        #: 按「语言对 -> [(source, translated, created_at), ...]」分组
        self._by_pair: dict[str, list[dict]] = {}
        #: 归一化源句 -> (language_pair, 译文) 快速精确命中索引
        self._by_normalized: dict[str, tuple[str, str]] = {}
        self._load()

    # ---- 持久化 ----

    def _load(self) -> None:
        """从磁盘加载记忆库；文件缺失/损坏时安全降级为空库。"""
        try:
            if not self._path.exists():
                return
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            entries = raw.get("entries", []) if isinstance(raw, dict) else []
            loaded = 0
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                source = entry.get("source")
                translated = entry.get("translated")
                if not isinstance(source, str) or not isinstance(translated, str):
                    continue
                if not source.strip() or not translated.strip():
                    continue
                language_pair = entry.get("language_pair", "")
                if not isinstance(language_pair, str):
                    language_pair = ""
                created_at = entry.get("created_at", time.time())
                self._by_pair.setdefault(language_pair, []).append(
                    {
                        "source": source.strip(),
                        "translated": translated.strip(),
                        "language_pair": language_pair,
                        "created_at": float(created_at),
                    }
                )
                loaded += 1
                if loaded >= self._max_entries:
                    break
            self._rebuild_normalized_index()
            logger.info(
                "Translation memory store loaded: {} entries from {}",
                loaded,
                self._path,
            )
        except Exception as exc:
            logger.warning(
                "Failed to load translation memory store from {}: {}",
                self._path,
                exc,
            )
            self._by_pair = {}
            self._by_normalized = {}

    def _persist(self) -> None:
        """原子写入记忆库（先写临时文件再替换，防半写损坏）。

        注意：调用方可能已持有 ``self._lock``（如 ``add``/``clear_pair``），
        因此这里不重新获取锁，直接读取内部状态；锁由调用方保证串行。
        """
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._path.with_suffix(".tmp")
            entries: list[dict] = []
            for pair_entries in self._by_pair.values():
                entries.extend(pair_entries)
            entries.sort(key=lambda item: item.get("created_at", 0), reverse=True)
            payload = {
                "version": 1,
                "updated_at": time.time(),
                "entries": entries[: self._max_entries],
            }
            tmp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp_path.replace(self._path)
        except Exception as exc:
            logger.error("Failed to persist translation memory store: {}", exc)

    def _rebuild_normalized_index(self) -> None:
        """重建「归一化源句 -> (语言对, 译文)」精确索引。"""
        from services.translation_memory import normalize_text

        index: dict[str, tuple[str, str]] = {}
        for language_pair, entries in self._by_pair.items():
            for entry in entries:
                normalized = normalize_text(entry["source"])
                if normalized:
                    # 同源句多语言对时保留最近写入的一条（按创建时间）。
                    existing = index.get(normalized)
                    if existing is None or entry["created_at"] >= existing[1]:
                        index[normalized] = (language_pair, entry["translated"])
        self._by_normalized = index

    # ---- 查询 ----

    def lookup(self, source: str, language_pair: str = "") -> Optional[dict]:
        """精确查询持久化记忆库中的句对。

        Args:
            source: 源句原文。
            language_pair: 语言对（如 "en->zh-CN"）；非空时要求一致。

        Returns:
            命中时返回句对字典副本；未命中返回 None。
        """
        from services.translation_memory import normalize_text

        normalized = normalize_text(source)
        if not normalized:
            return None
        with self._lock:
            hit = self._by_normalized.get(normalized)
            if hit is None:
                return None
            hit_pair, translated = hit
            if language_pair and hit_pair and hit_pair != language_pair:
                return None
            return {
                "source": source,
                "translated": translated,
                "language_pair": hit_pair,
                "created_at": 0.0,
            }

    def all_entries(self, *, limit: int = 200) -> list[dict]:
        """返回记忆库句对列表（按语言对分组后按创建时间倒序）。

        Args:
            limit: 返回的最大条目数。

        Returns:
            句对字典列表（副本）。
        """
        with self._lock:
            entries: list[dict] = []
            for pair_entries in self._by_pair.values():
                entries.extend(pair_entries)
        entries.sort(key=lambda item: item.get("created_at", 0), reverse=True)
        return [dict(entry) for entry in entries[: max(1, limit)]]

    def pair_entries(self, language_pair: str, *, limit: int = 500) -> list[dict]:
        """返回指定语言对的句对列表（按创建时间倒序）。"""
        with self._lock:
            entries = list(self._by_pair.get(language_pair, []))
        entries.sort(key=lambda item: item.get("created_at", 0), reverse=True)
        return [dict(entry) for entry in entries[: max(1, limit)]]

    def size(self) -> int:
        """当前句对总数。"""
        with self._lock:
            return sum(len(entries) for entries in self._by_pair.values())

    def size_by_pair(self, language_pair: str) -> int:
        """指定语言对的句对数。"""
        with self._lock:
            return len(self._by_pair.get(language_pair, []))

    def stats(self) -> dict[str, object]:
        """汇总统计（供 REST 端点展示）。"""
        with self._lock:
            pairs = {pair: len(entries) for pair, entries in self._by_pair.items()}
        return {
            "size": sum(pairs.values()),
            "pairs": len(pairs),
            "by_pair": dict(sorted(pairs.items(), key=lambda item: -item[1])),
        }

    # ---- 写入 ----

    def add(
        self,
        source: str,
        translated: str,
        language_pair: str = "",
    ) -> bool:
        """写入一个句对到持久化记忆库（跨会话累积）。

        精确重复句对（同语言对 + 归一化源句一致）直接更新译文，
        并把该条目移到列表末尾（视为最近写入，倒序优先展示）。

        Args:
            source: 源句原文。
            translated: 译文。
            language_pair: 语言对标识（如 "en->zh-CN"）。

        Returns:
            是否确实写入（空输入或超过容量上限时返回 False）。
        """
        from services.translation_memory import normalize_text

        source_norm = normalize_text(source)
        if not source_norm or not translated.strip():
            return False

        with self._lock:
            pair_entries = self._by_pair.setdefault(language_pair, [])
            for index, entry in enumerate(pair_entries):
                if normalize_text(entry["source"]) == source_norm:
                    entry["source"] = source.strip()
                    entry["translated"] = translated.strip()
                    entry["created_at"] = time.time()
                    # 移到末尾（最近写入）
                    pair_entries.append(pair_entries.pop(index))
                    self._by_normalized[source_norm] = (language_pair, translated.strip())
                    self._persist()
                    return True

            # 新增：容量保护（全部语言对共享上限）
            total = sum(len(entries) for entries in self._by_pair.values())
            if total >= self._max_entries:
                logger.warning(
                    "Translation memory store at capacity ({} entries); skipping write",
                    total,
                )
                return False

            pair_entries.append(
                {
                    "source": source.strip(),
                    "translated": translated.strip(),
                    "language_pair": language_pair,
                    "created_at": time.time(),
                }
            )
            self._by_normalized[source_norm] = (language_pair, translated.strip())
            self._persist()
            return True

    def clear_pair(self, language_pair: str) -> int:
        """清空指定语言对的句对。

        Args:
            language_pair: 语言对标识。

        Returns:
            清空的句对数。
        """
        with self._lock:
            entries = self._by_pair.pop(language_pair, [])
            if entries:
                self._rebuild_normalized_index()
                self._persist()
        return len(entries)

    def clear_all(self) -> int:
        """清空全部句对（隐私控制/用户手动清空）。

        Returns:
            清空的句对数。
        """
        with self._lock:
            count = sum(len(entries) for entries in self._by_pair.values())
            self._by_pair.clear()
            self._by_normalized.clear()
            if count:
                self._persist()
        return count


#: 全局翻译记忆库持久化存储（单例，进程内共享）。
_tm_store: Optional[TranslationMemoryStore] = None


def get_tm_store() -> Optional[TranslationMemoryStore]:
    """返回全局翻译记忆库持久化存储（未初始化时返回 None）。"""
    return _tm_store


def set_tm_store(store: Optional[TranslationMemoryStore]) -> None:
    """设置全局翻译记忆库持久化存储（应用启动时调用）。"""
    global _tm_store
    _tm_store = store
