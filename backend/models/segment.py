"""上下文管理器和 Segment 数据模型"""

from dataclasses import dataclass, field
from typing import Literal, Optional, Deque
from collections import deque
import time


@dataclass
class Revision:
    """修正记录"""
    old_text: str
    new_text: str
    reason: Literal["asr_correction", "translation_correction"]
    timestamp: float = field(default_factory=time.time)


@dataclass
class Segment:
    """单个语音段落"""

    id: str
    text_asr: str
    confidence: float
    source_language: str = "en"
    target_language: str = "zh-CN"
    text_translated: str = ""
    status: Literal["draft", "final", "revised"] = "draft"
    timestamp: float = field(default_factory=time.time)
    revised_at: Optional[float] = None
    revision_history: list[Revision] = field(default_factory=list)
    speaker_id: str = ""

    def apply_revision(self, new_text: str, reason: str) -> None:
        """应用修正"""
        self.revision_history.append(Revision(
            old_text=self.text_translated,
            new_text=new_text,
            reason=reason,
        ))
        self.text_translated = new_text
        self.status = "revised"
        self.revised_at = time.time()


@dataclass
class ContextWindow:
    """上下文滑动窗口"""

    session_id: str
    segments: Deque[Segment] = field(default_factory=lambda: deque(maxlen=20))
    current_buffer: str = ""  # 当前正在构建的句子
    window_size: int = 10
    summary: str = ""  # 更早上下文的压缩摘要（分层上下文用，可为空）

    def add_segment(self, segment: Segment) -> None:
        """添加新段落到窗口"""
        self.segments.append(segment)

    def get_recent(self, n: int) -> list[Segment]:
        """获取最近 n 个段落"""
        return list(self.segments)[-n:]

    def get_all(self) -> list[Segment]:
        """获取所有段落"""
        return list(self.segments)

    def get_by_id(self, segment_id: str) -> Optional[Segment]:
        """根据 ID 获取段落"""
        for seg in self.segments:
            if seg.id == segment_id:
                return seg
        return None

    def update_segment(self, segment: Segment) -> None:
        """更新段落"""
        for i, seg in enumerate(self.segments):
            if seg.id == segment.id:
                self.segments[i] = segment
                return

    def to_context_text(
        self,
        max_sentences: int = 8,
        recent_sentences: int = 3,
        older_max_chars: int = 40,
    ) -> str:
        """将窗口内容格式化为 NMT 可用的分层上下文字符串。

        分层策略（用于降低 input token 成本）：
        - 最近 ``recent_sentences`` 句保留完整原文（保证指代衔接）；
        - 更早的句子压缩为每句前缀（超出 ``older_max_chars`` 截断），
          保留主题连贯性但大幅减少 token。
        - 若存在 ``summary``（外部构建的更早上下文摘要），优先使用它。

        Args:
            max_sentences: 参与上下文的总句数上限。
            recent_sentences: 保留完整原文的最近句数。
            older_max_chars: 早句压缩长度上限（字符）。

        Returns:
            拼接后的上下文字符串。
        """
        all_segments = list(self.segments)
        if not all_segments:
            return ""

        recent = all_segments[-recent_sentences:] if all_segments else []
        older = all_segments[: -recent_sentences] if len(all_segments) > recent_sentences else []
        older = older[-max(0, max_sentences - recent_sentences):]

        lines: list[str] = []
        if self.summary:
            lines.append(self.summary)

        for seg in older:
            source = compress_text(seg.text_asr, older_max_chars)
            lines.append(f"[{seg.source_language.upper()}] {source}")
            if seg.text_translated:
                target = compress_text(seg.text_translated, older_max_chars)
                lines.append(f"[{seg.target_language.upper()}] {target}")

        for seg in recent:
            lines.append(f"[{seg.source_language.upper()}] {seg.text_asr}")
            if seg.text_translated:
                lines.append(f"[{seg.target_language.upper()}] {seg.text_translated}")
        return "\n".join(lines)


def compress_text(text: str, max_chars: int) -> str:
    """压缩文本到指定长度，截断处加省略号。

    Args:
        text: 待压缩文本。
        max_chars: 压缩后最大字符数。

    Returns:
        未超长时返回原文；超长时返回截断并追加 "…"。
    """
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}…"
