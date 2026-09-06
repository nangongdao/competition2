"""会话学习摘要服务单元测试。

覆盖：
- 空会话摘要（零成本本地模式）
- 关键词提取（停用词过滤 / TOP N / 代表句）
- 时长 / 修正数 / 说话人数统计
- LLM 增强摘要成功路径
- LLM 失败时静默降级为本地摘要（不中断请求）
- 摘要负载可 JSON 序列化
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from models.segment import ContextWindow, Segment
from services.session_summary import (
    SessionSummaryService,
    extract_keywords,
)


def _make_segment(
    text_asr: str,
    *,
    text_translated: str = "",
    timestamp: float = 0.0,
    speaker_id: str = "",
    status: str = "final",
    revised_at: float | None = None,
) -> Segment:
    return Segment(
        id=f"seg-{abs(hash(text_asr))}",
        text_asr=text_asr,
        confidence=0.9,
        text_translated=text_translated,
        timestamp=timestamp,
        speaker_id=speaker_id,
        status=status,  # type: ignore[arg-type]
        revised_at=revised_at,
    )


def _window(*segments: Segment) -> ContextWindow:
    window = ContextWindow(session_id="test-session")
    for seg in segments:
        window.add_segment(seg)
    return window


class ExtractKeywordsTests(unittest.TestCase):
    def test_empty_window_returns_empty_keywords(self) -> None:
        self.assertEqual(extract_keywords([]), [])

    def test_stopwords_filtered(self) -> None:
        segments = [
            _make_segment("the and or of a an it is are"),
            _make_segment("another this that with from by"),
        ]
        keywords = extract_keywords(segments)
        # 全部是停用词 -> 无关键词
        self.assertEqual(keywords, [])

    def test_frequent_term_ranked_first(self) -> None:
        segments = [
            _make_segment("Kubernetes helps orchestrate containers"),
            _make_segment("Kubernetes scales containers automatically"),
            _make_segment("Kubernetes manages container clusters"),
        ]
        keywords = extract_keywords(segments, top_n=3)
        self.assertTrue(keywords)
        self.assertEqual(keywords[0].term, "kubernetes")
        self.assertEqual(keywords[0].count, 3)

    def test_keyword_examples_attached(self) -> None:
        segments = [
            _make_segment("Machine learning improves translation quality"),
            _make_segment("Machine learning needs labeled data"),
            _make_segment("Machine learning powers the revision engine"),
        ]
        keywords = extract_keywords(segments, top_n=2)
        machine = next(kw for kw in keywords if kw.term == "machine")
        self.assertTrue(machine.examples)
        self.assertLessEqual(len(machine.examples), 2)

    def test_top_n_respected(self) -> None:
        segments = [
            _make_segment("alpha beta gamma delta"),
            _make_segment("alpha beta gamma"),
            _make_segment("alpha beta"),
            _make_segment("alpha"),
        ]
        keywords = extract_keywords(segments, top_n=2)
        self.assertLessEqual(len(keywords), 2)
        self.assertEqual(keywords[0].term, "alpha")

    def test_chinese_terms_extracted(self) -> None:
        segments = [
            _make_segment("人工智能正在改变翻译行业"),
            _make_segment("人工智能需要大量训练数据"),
        ]
        keywords = extract_keywords(segments, top_n=5)
        terms = {kw.term for kw in keywords}
        self.assertTrue(any("人工" in term or "智能" in term for term in terms))


class SessionSummaryServiceTests(unittest.TestCase):
    def _build_service(self) -> SessionSummaryService:
        return SessionSummaryService()

    def test_empty_session_summary(self) -> None:
        service = self._build_service()
        summary = asyncio.run(service.build_summary("s1", _window(), use_llm=False))
        self.assertEqual(summary.mode, "local")
        self.assertEqual(summary.segment_count, 0)
        self.assertEqual(summary.keywords, [])
        self.assertEqual(summary.bullets, [])

    def test_stats_computed(self) -> None:
        segments = [
            _make_segment(
                "First sentence about Kubernetes",
                timestamp=100.0,
                status="revised",
                revised_at=105.0,
            ),
            _make_segment(
                "Second sentence about Docker",
                timestamp=120.0,
                speaker_id="speaker_1",
            ),
            _make_segment(
                "Third sentence about containers",
                timestamp=140.0,
                speaker_id="speaker_2",
            ),
        ]
        service = self._build_service()
        summary = asyncio.run(service.build_summary("s1", _window(*segments), use_llm=False))
        self.assertEqual(summary.segment_count, 3)
        self.assertEqual(summary.revision_count, 1)
        self.assertEqual(summary.speaker_count, 2)
        self.assertAlmostEqual(summary.duration_seconds, 40.0, places=1)
        self.assertTrue(summary.keywords)

    def test_llm_summary_success(self) -> None:
        service = self._build_service()
        nmt = AsyncMock()
        nmt.complete_text.return_value = (
            "- Kubernetes 编排容器\n"
            "- 自动化扩缩容\n"
            "[行动] 部署生产集群\n"
            "[行动] 补充监控告警\n"
        )
        service.attach_nmt(nmt)  # type: ignore[arg-type]

        segments = [
            _make_segment("Kubernetes orchestrates containers", text_translated="Kubernetes 编排容器"),
            _make_segment("It scales automatically", text_translated="它自动扩缩容"),
            _make_segment("We deploy to production", text_translated="我们部署到生产"),
        ]
        summary = asyncio.run(service.build_summary("s1", _window(*segments), use_llm=True))
        self.assertEqual(summary.mode, "llm")
        self.assertGreaterEqual(len(summary.bullets), 2)
        self.assertGreaterEqual(len(summary.action_items), 1)

    def test_llm_failure_falls_back_to_local(self) -> None:
        service = self._build_service()
        nmt = AsyncMock()
        nmt.complete_text.side_effect = RuntimeError("upstream down")
        service.attach_nmt(nmt)  # type: ignore[arg-type]

        segments = [
            _make_segment("Kubernetes orchestrates containers"),
            _make_segment("It scales automatically"),
            _make_segment("We deploy to production"),
        ]
        summary = asyncio.run(service.build_summary("s1", _window(*segments), use_llm=True))
        self.assertEqual(summary.mode, "local")
        self.assertTrue(summary.keywords)
        self.assertEqual(summary.bullets, [])

    def test_llm_not_attached_uses_local(self) -> None:
        service = self._build_service()
        segments = [
            _make_segment("Kubernetes orchestrates containers"),
            _make_segment("It scales automatically"),
            _make_segment("We deploy to production"),
        ]
        summary = asyncio.run(service.build_summary("s1", _window(*segments), use_llm=True))
        self.assertEqual(summary.mode, "local")

    def test_summary_serializable(self) -> None:
        segments = [
            _make_segment("Kubernetes orchestrates containers", text_translated="Kubernetes 编排容器"),
            _make_segment("It scales automatically", text_translated="它自动扩缩容"),
        ]
        service = self._build_service()
        summary = asyncio.run(service.build_summary("s1", _window(*segments), use_llm=False))
        payload = json.dumps(summary.to_dict(), ensure_ascii=False)
        parsed = json.loads(payload)
        self.assertEqual(parsed["session_id"], "s1")
        self.assertIn("keywords", parsed)


if __name__ == "__main__":
    unittest.main()
