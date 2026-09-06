"""翻译记忆库（Translation Memory, V5.3）。

对已翻译过的句对建立索引，翻译新句子时先查记忆库：
- 相似句子直接复用已翻译结果，避免重复调用翻译 API（省成本、降延迟）。
- 未命中时正常翻译，翻译完成后自动把句对写回记忆库，持续累积。

设计约束（与 ROADMAP V5.3 对齐）：
- 不引入向量数据库（ChromaDB 等）重依赖 —— 同传场景句子短、语序稳定，
  使用「归一化 + 字符级相似度 + 词袋 Jaccard」组合判定，纯标准库实现，
  单次匹配在毫秒级，足够实时管线使用。
- 每个会话独立记忆库实例（不跨用户/不跨会话串扰），会话结束即释放。
- 相似度阈值可配置；过短句子（<= 阈值字符）不做模糊匹配，避免误命中。
- 大小写与标点归一化，提升命中率；命中时返回源句/译句供前端展示来源。
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Optional

from services.translation_memory_store import TranslationMemoryStore


#: 归一化后仍短于该长度的句子不做模糊匹配（误命中风险高）
MIN_MATCH_CHARS = 6
#: 默认相似度阈值：>= 该值判定为命中并复用翻译
DEFAULT_SIMILARITY_THRESHOLD = 0.82
#: 单个会话记忆库最大句对数，防止超长会话内存膨胀
MAX_ENTRIES = 2000
#: 单次匹配扫描的最大句对数（性能上限）
MAX_SCAN_ENTRIES = 500

#: 归一化时移除的标点与空白
_PUNCT_RE = re.compile(r"[\s，。！？；：、“”‘’（）【】《》〈〉…—·,.;:!?()\[\]{}\"']+")
#: 提取词袋 token 用（英文单词 / 连续中文片段）
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9'_-]*|[\u4e00-\u9fff]+")


def normalize_text(text: str) -> str:
    """归一化句子：小写 + 去除标点空白，用于相似度比较。"""
    return _PUNCT_RE.sub(" ", text).strip().lower()


def character_similarity(left: str, right: str) -> float:
    """字符级相似度（对称）：基于公共字符序列比例。

    使用最长公共子序列（LCS）长度归一化到两串平均长度，
    对语序敏感（同传句子顺序重要），比单纯的字符集合相似更准确。

    Args:
        left: 已归一化的源串。
        right: 已归一化的候选串。

    Returns:
        0.0 ~ 1.0 的相似度。
    """
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0

    m, n = len(left), len(right)
    # 滚动数组优化 LCS 空间（O(min(m,n))）
    if m < n:
        left, right = right, left
        m, n = n, m
    prev = [0] * (n + 1)
    curr = [0] * (n + 1)
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if left[i - 1] == right[j - 1]:
                curr[j] = prev[j - 1] + 1
            else:
                curr[j] = prev[j] if prev[j] >= curr[j - 1] else curr[j - 1]
        prev, curr = curr, prev
    lcs_len = prev[n]
    return (2.0 * lcs_len) / (m + n)


def token_jaccard_similarity(left: str, right: str) -> float:
    """词袋 Jaccard 相似度：用于与字符相似度互补。

    语序变化但用词相近时，字符 LCS 可能偏低而 Jaccard 偏高；
    两者加权组合能同时兼顾「用词相同」与「语序相近」。

    Args:
        left: 已归一化的源串。
        right: 已归一化的候选串。

    Returns:
        0.0 ~ 1.0 的相似度。
    """
    left_tokens = set(_TOKEN_RE.findall(left))
    right_tokens = set(_TOKEN_RE.findall(right))
    if not left_tokens or not right_tokens:
        return 0.0
    union = left_tokens | right_tokens
    if not union:
        return 0.0
    return len(left_tokens & right_tokens) / len(union)


@dataclass(frozen=True)
class TMMatch:
    """翻译记忆库命中结果。"""

    source: str
    translated: str
    similarity: float
    matched_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        """转换为可 JSON 序列化的字典。"""
        return {
            "source": self.source,
            "translated": self.translated,
            "similarity": round(self.similarity, 4),
            "matched_at": self.matched_at,
        }


@dataclass(frozen=True)
class TMEntry:
    """记忆库句对条目。"""

    source: str
    translated: str
    language_pair: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        """转换为可 JSON 序列化的字典。"""
        return {
            "source": self.source,
            "translated": self.translated,
            "language_pair": self.language_pair,
            "created_at": self.created_at,
        }


class TranslationMemoryService:
    """会话级翻译记忆库（V5.3，含跨会话持久化联动）。

    线程/协程安全：所有读写都发生在单一事件循环内（由 Pipeline 串行调用），
    无需加锁；对外提供同步接口便于单元测试。

    V5.3 生产化补全：绑定可选持久化层 ``store`` 后，
    - ``lookup`` 先查会话级索引，未命中再查跨会话持久化库（相似句直接复用
      历史译文，跨场累积「越用越准、越用越省」）；
    - ``add`` 写回会话级索引的同时联动写入持久化库，重启不丢失。

    属性:
        session_id: 关联的会话标识（仅用于诊断日志）。
        store: 跨会话持久化存储（可为 None 表示仅会话级）。
    """

    def __init__(
        self,
        *,
        session_id: str = "",
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        store: TranslationMemoryStore | None = None,
    ) -> None:
        self.session_id = session_id
        self._threshold = similarity_threshold
        self._store = store
        #: 按「归一化源句 -> 条目」索引，快速精确命中
        self._by_normalized: dict[str, TMEntry] = {}
        #: 按创建顺序排列的条目列表（用于模糊扫描与容量裁剪）
        self._entries: list[TMEntry] = []
        self._hits = 0
        self._misses = 0
        self._written = 0

    @property
    def store(self) -> TranslationMemoryStore | None:
        """当前绑定的跨会话持久化存储。"""
        return self._store

    def attach_store(self, store: TranslationMemoryStore | None) -> None:
        """绑定/解绑跨会话持久化存储（V5.3 生产化）。

        Args:
            store: 持久化存储实例；传 None 关闭持久化联动。
        """
        self._store = store

    @property
    def enabled(self) -> bool:
        """记忆库功能是否可用（会话级实例恒可用）。"""
        return True

    @property
    def size(self) -> int:
        """当前句对数。"""
        return len(self._entries)

    @property
    def stats(self) -> dict[str, object]:
        """匹配统计（供会话诊断与前端展示）。"""
        return {
            "size": self.size,
            "hits": self._hits,
            "misses": self._misses,
            "written": self._written,
            "threshold": self._threshold,
        }

    def lookup(self, text: str, language_pair: str = "") -> Optional[TMMatch]:
        """查询翻译记忆：先精确匹配，再模糊匹配。

        Args:
            text: 待翻译的源句原文。
            language_pair: 语言对（如 "en->zh-CN"）；非空时要求条目语言对一致。

        Returns:
            命中时返回 TMMatch（含源句/译句/相似度）；未命中返回 None。
        """
        normalized = normalize_text(text)
        if not normalized:
            return None

        # 1) 精确命中（归一化后完全一致）——先查会话级索引
        exact = self._by_normalized.get(normalized)
        if exact is not None and self._pair_matches(exact, language_pair):
            self._hits += 1
            return TMMatch(
                source=exact.source,
                translated=exact.translated,
                similarity=1.0,
            )

        # 1.5) 跨会话持久化库精确命中（V5.3 生产化）——复用历史译文
        if self._store is not None:
            stored = self._store.lookup(text, language_pair=language_pair)
            if stored is not None and stored.get("translated"):
                self._hits += 1
                return TMMatch(
                    source=stored.get("source") or text,
                    translated=stored["translated"],
                    similarity=1.0,
                )

        # 2) 模糊匹配：过短句子不做，避免误命中
        if len(normalized) < MIN_MATCH_CHARS:
            self._misses += 1
            return None

        best: Optional[TMMatch] = None
        scanned = 0
        for entry in reversed(self._entries[-MAX_SCAN_ENTRIES:]):
            if not self._pair_matches(entry, language_pair):
                continue
            candidate_normalized = normalize_text(entry.source)
            if not candidate_normalized:
                continue
            char_sim = character_similarity(normalized, candidate_normalized)
            if char_sim >= self._threshold:
                jaccard_sim = token_jaccard_similarity(normalized, candidate_normalized)
                combined = 0.7 * char_sim + 0.3 * jaccard_sim
                if best is None or combined > best.similarity:
                    best = TMMatch(
                        source=entry.source,
                        translated=entry.translated,
                        similarity=combined,
                    )
            scanned += 1
            if scanned >= MAX_SCAN_ENTRIES:
                break

        if best is not None:
            self._hits += 1
            return best

        self._misses += 1
        return None

    def add(self, source: str, translated: str, language_pair: str = "") -> None:
        """写入一个句对到记忆库。

        精确重复句对直接更新译文（修正后的译文覆盖旧值），
        并保持插入顺序靠前，便于模糊扫描优先命中最近的翻译。

        Args:
            source: 源句原文。
            translated: 译文。
            language_pair: 语言对标识（如 "en->zh-CN"）。
        """
        source_norm = normalize_text(source)
        if not source_norm or not translated.strip():
            return

        entry = TMEntry(
            source=source.strip(),
            translated=translated.strip(),
            language_pair=language_pair,
        )

        existing_index: Optional[int] = None
        for index, existing in enumerate(self._entries):
            if normalize_text(existing.source) == source_norm:
                existing_index = index
                break

        if existing_index is not None:
            self._entries[existing_index] = entry
        else:
            self._entries.append(entry)
            if len(self._entries) > MAX_ENTRIES:
                self._entries.pop(0)

        self._by_normalized[source_norm] = entry
        self._written += 1

        # V5.3 生产化：联动写入跨会话持久化存储（重启不丢失）
        if self._store is not None:
            self._store.add(
                entry.source,
                entry.translated,
                language_pair=language_pair,
            )

    def clear(self) -> None:
        """清空记忆库（会话结束或用户手动清空）。"""
        self._by_normalized.clear()
        self._entries.clear()
        self._hits = 0
        self._misses = 0
        self._written = 0

    def export_entries(self, limit: int = 200) -> list[dict]:
        """导出记忆库句对（供前端展示/备份）。

        Args:
            limit: 返回的最大条目数。

        Returns:
            按创建时间倒序的句对字典列表。
        """
        return [entry.to_dict() for entry in reversed(self._entries[-limit:])]

    def load_entries(self, entries: list[dict]) -> int:
        """批量导入句对（如从备份恢复）。

        注意：批量导入仅写入会话级索引，不联动持久化层（避免把一次性
        测试/恢复数据污染跨会话记忆库）；如需持久化使用
        ``store.add`` 或专门恢复流程。

        Args:
            entries: 句对字典列表（source / translated / language_pair）。

        Returns:
            实际导入的条目数。
        """
        imported = 0
        for raw in entries:
            if not isinstance(raw, dict):
                continue
            source = raw.get("source")
            translated = raw.get("translated")
            if not isinstance(source, str) or not isinstance(translated, str):
                continue
            if not source.strip() or not translated.strip():
                continue
            language_pair = raw.get("language_pair", "")
            if not isinstance(language_pair, str):
                language_pair = ""
            self.add(source, translated, language_pair)
            imported += 1
        return imported

    def to_json(self) -> str:
        """序列化为 JSON 文本（持久化 / 备份）。"""
        payload = {
            "version": 1,
            "session_id": self.session_id,
            "threshold": self._threshold,
            "entries": self.export_entries(limit=MAX_ENTRIES),
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _pair_matches(self, entry: TMEntry, language_pair: str) -> bool:
        """判断条目语言对是否匹配查询条件。"""
        if not language_pair or not entry.language_pair:
            return True
        return entry.language_pair == language_pair

    def _reset_for_test(self) -> None:
        """仅供测试：重置计数。"""
        self._hits = 0
        self._misses = 0
        self._written = 0


def build_language_pair(source: str, target: str) -> str:
    """构造语言对标识（用于记忆库条目归属）。"""
    return f"{source}->{target}"
