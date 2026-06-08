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

    def to_context_text(self, max_sentences: int = 8) -> str:
        """将窗口内容格式化为 NMT 可用的上下文字符串"""
        recent = self.get_recent(max_sentences)
        lines = []
        for seg in recent:
            lines.append(f"[{seg.source_language.upper()}] {seg.text_asr}")
            if seg.text_translated:
                lines.append(f"[{seg.target_language.upper()}] {seg.text_translated}")
        return "\n".join(lines)
