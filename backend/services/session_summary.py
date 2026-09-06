"""会话学习摘要服务。

ROADMAP 阶段 9「内容沉淀与学习辅助」（AC-G7）：
观看结束后直接得到学习产物（摘要 / 关键词 / 行动项），而不是只剩看过的过程。

两种生成模式：
1. **本地统计摘要**（默认、零成本、离线可用）：
   - 会话时长 / 句数 / 修正数 / 说话人数
   - 高频关键词 TOP N（轻量 TF 加权，纯标准库实现，无外部依赖）
   - 每个关键词关联的代表句（供上下文跳转）
2. **LLM 增强摘要**（可选，复用 NMTService 的 LLM 客户端）：
   - 生成 3-5 条中文要点 + 关键词 + 行动项
   - LLM 调用失败时静默降级为本地统计摘要，绝不中断请求
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Optional

from loguru import logger

from models.segment import ContextWindow
from services.nmt_service import NMTService


#: 摘要端点返回的关键词条数上限
DEFAULT_KEYWORD_TOP_N = 8
#: 每个关键词最多关联的代表句数
KEYWORD_EXAMPLE_LIMIT = 2
#: LLM 生成要点条数
SUMMARY_BULLET_COUNT = 5
#: 参与关键词统计的句子数量上限（防止超长会话内存/耗时膨胀）
SUMMARY_MAX_SENTENCES = 800
#: 单句参与关键词统计的最大字符数
SUMMARY_MAX_SENTENCE_CHARS = 200

#: 常见停用词（中英文混合，统计关键词时过滤）
STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "at",
    "for", "with", "is", "are", "was", "were", "be", "been", "being",
    "this", "that", "these", "those", "it", "its", "as", "by", "from",
    "we", "you", "i", "he", "she", "they", "them", "his", "her", "their",
    "our", "my", "your", "not", "so", "if", "then", "than", "just",
    "very", "really", "about", "into", "over", "after", "before",
    "can", "will", "would", "could", "should", "shall", "may", "might",
    "do", "does", "did", "have", "has", "had", "get", "got", "go", "going",
    "make", "make", "say", "says", "said", "see", "think", "know",
    "one", "two", "three", "first", "second", "now", "also", "well", "like",
    "thing", "things", "way", "ways", "something", "somebody", "someone",
    "everyone", "everybody", "okay", "ok", "yes", "no", "yeah", "right",
    "actually", "basically", "kind", "sort", "lot", "lots", "much", "many",
    "more", "most", "because", "but", "what", "which", "who", "when", "where",
    "how", "why", "all", "any", "some", "each", "every", "other", "another",
    "的", "了", "和", "是", "在", "有", "我", "你", "他", "她", "它", "们",
    "这", "那", "就", "都", "而", "及", "与", "或", "一个", "我们", "你们",
    "他们", "她们", "它们", "这个", "那个", "这些", "那些", "什么", "怎么",
    "为什么", "因为", "所以", "但是", "不过", "如果", "然后", "现在", "可以",
    "会", "能", "要", "让", "把", "被", "对", "从", "到", "跟", "给", "为",
    "着", "过", "之", "其", "也", "还", "再", "又", "很", "更", "最", "太",
})


@dataclass(frozen=True)
class KeywordEntry:
    """关键词条目。"""

    term: str
    count: int
    examples: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SessionSummary:
    """会话学习摘要（与 REST 响应 JSON 一一对应）。"""

    session_id: str
    mode: str  # "local" | "llm"
    generated_at: float
    duration_seconds: float = 0.0
    segment_count: int = 0
    revision_count: int = 0
    speaker_count: int = 0
    keywords: list[KeywordEntry] = field(default_factory=list)
    bullets: list[str] = field(default_factory=list)
    action_items: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """转换为可 JSON 序列化的字典。"""
        return {
            "session_id": self.session_id,
            "mode": self.mode,
            "generated_at": self.generated_at,
            "duration_seconds": round(self.duration_seconds, 1),
            "segment_count": self.segment_count,
            "revision_count": self.revision_count,
            "speaker_count": self.speaker_count,
            "keywords": [
                {"term": kw.term, "count": kw.count, "examples": kw.examples}
                for kw in self.keywords
            ],
            "bullets": self.bullets,
            "action_items": self.action_items,
        }


#: 从句子中提取候选关键词的正则（英文单词 / 中文连续片段 / 数字技术名词）
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,}|[\u4e00-\u9fff]{2,6}|\b\d{2,4}[a-z]?\b", re.IGNORECASE)


def extract_keywords(
    segments: list,
    *,
    top_n: int = DEFAULT_KEYWORD_TOP_N,
) -> list[KeywordEntry]:
    """从片段列表中提取高频关键词（轻量 TF 加权，无外部依赖）。

    策略：
    - 对每个片段按词频计数，避免长句重复刷屏
    - 过滤停用词与过短/过长的词
    - 取出现片段数最多的 TOP N，每个关键词附 1-2 条代表句

    Args:
        segments: 会话片段（含 text_asr / text_translated 属性）。
        top_n: 返回的关键词条数上限。

    Returns:
        按出现片段数降序排列的关键词列表。
    """
    term_docs: dict[str, set[int]] = {}
    doc_texts: dict[int, str] = {}

    limited = segments[-SUMMARY_MAX_SENTENCES:]
    for index, seg in enumerate(limited):
        text = (seg.text_asr or "")[:SUMMARY_MAX_SENTENCE_CHARS]
        if not text.strip():
            continue
        doc_texts[index] = seg.text_asr or ""

        seen: set[str] = set()
        for token in _TOKEN_RE.findall(text):
            lowered = token.lower()
            if len(lowered) < 2 or lowered in STOPWORDS:
                continue
            # 数字单独出现时不算关键词（除非是版本号如 v2 / gpt4 等）
            if lowered.isdigit():
                continue
            if lowered in seen:
                continue
            seen.add(lowered)
            term_docs.setdefault(lowered, set()).add(index)

    ranked = sorted(
        ((len(docs), term) for term, docs in term_docs.items()),
        reverse=True,
    )[:top_n]

    keywords: list[KeywordEntry] = []
    for count, term in ranked:
        doc_indexes = sorted(term_docs[term])
        examples: list[str] = []
        for idx in doc_indexes[:KEYWORD_EXAMPLE_LIMIT]:
            snippet = doc_texts.get(idx, "")
            if snippet:
                examples.append(snippet[:120])
        keywords.append(KeywordEntry(term=term, count=count, examples=examples))
    return keywords


class SessionSummaryService:
    """生成会话学习摘要。

    不持有 Redis 连接：读取窗口由调用方（路由层）注入 ContextWindow，
    便于复用现有上下文读取逻辑与测试 mock。
    """

    def __init__(self) -> None:
        self._nmt: Optional[NMTService] = None

    def attach_nmt(self, nmt: NMTService | None) -> None:
        """注入 NMT 服务（用于可选的 LLM 增强摘要）。"""
        self._nmt = nmt

    async def build_summary(
        self,
        session_id: str,
        window: ContextWindow,
        *,
        use_llm: bool = True,
    ) -> SessionSummary:
        """构建会话学习摘要。

        Args:
            session_id: 会话标识。
            window: 会话上下文窗口（含全部片段）。
            use_llm: 是否尝试 LLM 增强摘要；失败自动降级为本地统计摘要。

        Returns:
            会话学习摘要。
        """
        segments = window.get_all()
        keywords = extract_keywords(segments)

        summary = SessionSummary(
            session_id=session_id,
            mode="local",
            generated_at=time.time(),
            duration_seconds=self._compute_duration(window),
            segment_count=len(segments),
            revision_count=self._count_revisions(segments),
            speaker_count=self._count_speakers(segments),
            keywords=keywords,
            bullets=[],
            action_items=[],
        )

        if use_llm and self._nmt is not None and len(segments) >= 3:
            try:
                bullets, action_items = await self._generate_llm_summary(window)
                summary = SessionSummary(
                    session_id=session_id,
                    mode="llm",
                    generated_at=summary.generated_at,
                    duration_seconds=summary.duration_seconds,
                    segment_count=summary.segment_count,
                    revision_count=summary.revision_count,
                    speaker_count=summary.speaker_count,
                    keywords=keywords,
                    bullets=bullets,
                    action_items=action_items,
                )
            except Exception as exc:
                # LLM 摘要失败绝不中断请求：静默降级为本地统计摘要。
                logger.warning(
                    "LLM summary generation failed for {} ({}), falling back to local summary",
                    session_id,
                    exc,
                )

        return summary

    def _compute_duration(self, window: ContextWindow) -> float:
        segments = window.get_all()
        if not segments:
            return 0.0
        timestamps = [seg.timestamp for seg in segments if seg.timestamp]
        if not timestamps:
            return 0.0
        return max(0.0, max(timestamps) - min(timestamps))

    @staticmethod
    def _count_revisions(segments: list) -> int:
        return sum(
            1 for seg in segments
            if getattr(seg, "status", "") == "revised"
            or getattr(seg, "revised_at", None) is not None
        )

    @staticmethod
    def _count_speakers(segments: list) -> int:
        speakers = {seg.speaker_id for seg in segments if getattr(seg, "speaker_id", "")}
        return len(speakers)

    async def _generate_llm_summary(self, window: ContextWindow) -> tuple[list[str], list[str]]:
        """调用 LLM 生成要点与行动项（复用 NMTService 的 complete_text）。"""
        if self._nmt is None:
            return [], []

        transcript = self._build_transcript(window)
        if not transcript.strip():
            return [], []

        prompt = (
            "下面是某次演讲/会议的双语逐字稿（EN 原文 + ZH 译文）。\n"
            f"{transcript}\n\n"
            "请用目标语言（简体中文）输出：\n"
            f"1. {SUMMARY_BULLET_COUNT} 条要点总结（每条不超过 20 字，以「- 」开头）；\n"
            "2. 3 条可执行的行动项或待办（以「[行动] 」开头）。\n"
            "只输出这两部分，不要额外解释。"
        )
        system_prompt = (
            "You are a concise note-taking assistant. Summarize the meeting/lecture "
            "into bullet points and action items in Simplified Chinese. "
            "Do not include a preamble or trailing commentary."
        )
        raw = await self._nmt.complete_text(prompt, system_prompt=system_prompt)

        bullets: list[str] = []
        action_items: list[str] = []
        for line in raw.splitlines():
            stripped = line.strip().lstrip("-•*#").strip()
            if not stripped:
                continue
            if stripped.startswith("[行动]") or stripped.lower().startswith("action"):
                action_items.append(stripped.lstrip("[行动]").lstrip(":").strip())
            elif len(stripped) < 160:
                bullets.append(stripped)
        return bullets[: SUMMARY_BULLET_COUNT], action_items[:3]

    def _build_transcript(self, window: ContextWindow, max_chars: int = 4000) -> str:
        """构建供 LLM 摘要使用的双语逐字稿（限制长度控制 token 成本）。"""
        parts: list[str] = []
        used = 0
        for seg in window.get_all()[-40:]:
            source = (seg.text_asr or "").strip()
            target = (seg.text_translated or "").strip()
            if not source and not target:
                continue
            line = f"EN: {source}\nZH: {target}" if target else f"EN: {source}"
            if used + len(line) > max_chars:
                break
            parts.append(line)
            used += len(line)
        return "\n\n".join(parts)


def parse_summary_payload(raw: object) -> dict:
    """解析 /summary 响应负载（供测试与前端类型对齐）。"""
    if not isinstance(raw, dict):
        raise ValueError("summary payload must be a JSON object")
    return raw
