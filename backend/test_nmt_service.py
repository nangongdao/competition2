from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest


BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from models.segment import ContextWindow, Segment
from services.nmt_service import NMTService, MAX_RETRY_ATTEMPTS, RETRYABLE_STATUS_CODES, _is_retryable
from core.config import settings
from core.exceptions import NMTError


class FakeStream:
    def __init__(self, chunks: list[object]) -> None:
        self._chunks = chunks

    def __aiter__(self) -> FakeStream:
        self._iterator = iter(self._chunks)
        return self

    async def __anext__(self) -> object:
        try:
            return next(self._iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class FakeCompletions:
    def __init__(self, chunks: list[object]) -> None:
        self._chunks = chunks
        self.last_request: dict[str, object] | None = None

    async def create(self, **kwargs: object) -> FakeStream:
        self.last_request = kwargs
        return FakeStream(self._chunks)


class FakeOpenAIClient:
    def __init__(self, chunks: list[object]) -> None:
        self.completions = FakeCompletions(chunks)
        self.chat = SimpleNamespace(completions=self.completions)


class NMTServiceOpenAITests(unittest.IsolatedAsyncioTestCase):
    async def test_openai_stream_skips_empty_choices(self) -> None:
        service = NMTService()
        fake_client = FakeOpenAIClient([
            chunk_with_choices([]),
            chunk_with_content("早"),
            chunk_with_content("上"),
        ])
        service._client = fake_client

        tokens = await collect_tokens(service)

        self.assertEqual(tokens, ["早", "上", "<FINAL>"])
        self.assertTrue(fake_client.completions.last_request["stream"])

    async def test_openai_stream_skips_missing_or_empty_content(self) -> None:
        service = NMTService()
        service._client = FakeOpenAIClient([
            chunk_with_choice(SimpleNamespace(delta=None)),
            chunk_with_choice(SimpleNamespace(delta=SimpleNamespace())),
            chunk_with_content(""),
            chunk_with_content("你好"),
        ])

        tokens = await collect_tokens(service)

        self.assertEqual(tokens, ["你好", "<FINAL>"])


    async def test_openai_prompt_uses_segment_language_pair(self) -> None:
        service = NMTService()
        fake_client = FakeOpenAIClient([
            chunk_with_content("translated"),
        ])
        service._client = fake_client
        context = ContextWindow(session_id="test-session", window_size=10)
        current = Segment(
            id="test-1",
            text_asr="konnichiwa",
            confidence=1.0,
            source_language="ja",
            target_language="zh-CN",
        )

        tokens = [
            token
            async for token in service._translate_openai(context, current)
        ]

        self.assertEqual(tokens, ["translated", "<FINAL>"])
        request = fake_client.completions.last_request
        self.assertIsNotNone(request)
        if request is None:
            raise AssertionError("Expected OpenAI request metadata.")
        messages = request["messages"]
        self.assertIsInstance(messages, list)
        system_message = messages[0]["content"]
        user_message = messages[1]["content"]
        self.assertIn("Japanese speech to Simplified Chinese", system_message)
        self.assertIn("from Japanese to Simplified Chinese", user_message)

    async def test_system_prompt_includes_style_instruction(self) -> None:
        """阶段 3：翻译风格预设应注入 system prompt。"""
        service = NMTService()
        service.set_style_preset("faithful")
        fake_client = FakeOpenAIClient([
            chunk_with_content("translated"),
        ])
        service._client = fake_client
        context = ContextWindow(session_id="test-session", window_size=10)
        current = Segment(
            id="test-1",
            text_asr="hello world",
            confidence=1.0,
        )

        tokens = [
            token
            async for token in service._translate_openai(context, current)
        ]

        self.assertEqual(tokens, ["translated", "<FINAL>"])
        request = fake_client.completions.last_request
        self.assertIsNotNone(request)
        if request is None:
            raise AssertionError("Expected OpenAI request metadata.")
        messages = request["messages"]
        self.assertIsInstance(messages, list)
        system_message = messages[0]["content"]
        self.assertIn("FAITHFUL", system_message)
        self.assertIn("preserving", system_message)

    async def test_default_style_skips_extra_instruction(self) -> None:
        """默认简洁风格不应注入额外指令（与历史行为一致）。"""
        service = NMTService()
        fake_client = FakeOpenAIClient([
            chunk_with_content("translated"),
        ])
        service._client = fake_client
        context = ContextWindow(session_id="test-session", window_size=10)
        current = Segment(
            id="test-1",
            text_asr="hello world",
            confidence=1.0,
        )

        tokens = [
            token
            async for token in service._translate_openai(context, current)
        ]

        self.assertEqual(tokens, ["translated", "<FINAL>"])
        request = fake_client.completions.last_request
        self.assertIsNotNone(request)
        if request is None:
            raise AssertionError("Expected OpenAI request metadata.")
        messages = request["messages"]
        system_message = messages[0]["content"]
        self.assertNotIn("FAITHFUL", system_message)
        self.assertNotIn("LECTURE NOTES", system_message)

    def test_style_preset_property_tracks_update(self) -> None:
        service = NMTService()
        self.assertEqual(service.style_preset, "concise")
        service.set_style_preset("lecture")
        self.assertEqual(service.style_preset, "lecture")
        service.set_style_preset("unknown-style")
        self.assertEqual(service.style_preset, "concise")

    def test_rules_prompt_keeps_numbers_and_proper_nouns(self) -> None:
        """阶段 3：数字与专名稳定输出 —— 提示词规则包含数字/专名保持约束。"""
        from services.nmt_service import NMTService as NMT

        rules = NMT.RULES_PROMPT
        self.assertIn("numbers", rules.lower())
        self.assertIn("proper nouns", rules.lower())
        # 数字规则：不四舍五入、不增删数字
        self.assertIn("do not round", rules.lower())
        self.assertIn("digits", rules.lower())
        # 专名规则：保持原形，除非有通用中文译名
        self.assertIn("original form", rules.lower())


class RetryableFakeCompletions:
    """前 failure_count 次调用抛 429，之后正常返回流。"""

    def __init__(self, chunks: list[object], *, failure_count: int) -> None:
        self._chunks = chunks
        self._failure_count = failure_count
        self.calls = 0

    async def create(self, **kwargs: object) -> FakeStream:
        self.calls += 1
        if self.calls <= self._failure_count:
            raise NMTError("rate limited", status_code=429)
        return FakeStream(self._chunks)


class AlwaysFailCompletions:
    async def create(self, **kwargs: object) -> FakeStream:
        raise NMTError("server error", status_code=500)


async def collect_translate_stream_tokens(service: NMTService) -> list[str]:
    context = ContextWindow(session_id="test-session", window_size=10)
    current = Segment(
        id="test-1",
        text_asr="Good morning.",
        confidence=1.0,
    )
    return [
        token
        async for token in service.translate_stream(context, current)
    ]


class NMTServiceRetryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.service = NMTService()
        self.service._engine = "openai"

    async def test_retries_transient_errors_then_succeeds(self) -> None:
        completions = RetryableFakeCompletions(
            [chunk_with_content("早"), chunk_with_content("上好")],
            failure_count=2,
        )
        self.service._client = FakeOpenAIClient(chunks=[])
        self.service._client.chat.completions = completions

        tokens = await collect_translate_stream_tokens(self.service)

        self.assertEqual(tokens, ["早", "上好", "<FINAL>"])
        self.assertEqual(completions.calls, 3)  # 2 次失败 + 1 次成功

    async def test_degrades_to_source_text_after_exhausting_retries(self) -> None:
        self.service._client = SimpleNamespace(
            chat=SimpleNamespace(completions=AlwaysFailCompletions()),
        )

        tokens = await collect_translate_stream_tokens(self.service)

        self.assertEqual(tokens[0], "[未翻译] Good morning.")
        self.assertEqual(tokens[-1], "<FINAL>")

    async def test_non_retryable_error_degrades_immediately(self) -> None:
        class AuthErrorCompletions:
            async def create(self, **kwargs: object) -> FakeStream:
                raise NMTError("invalid api key", status_code=401)

        self.service._client = SimpleNamespace(
            chat=SimpleNamespace(completions=AuthErrorCompletions()),
        )

        tokens = await collect_translate_stream_tokens(self.service)

        self.assertEqual(tokens[0], "[未翻译] Good morning.")
        self.assertEqual(tokens[-1], "<FINAL>")

    def test_is_retryable_recognizes_status_codes(self) -> None:
        self.assertTrue(_is_retryable(NMTError("x", status_code=429)))
        self.assertTrue(_is_retryable(NMTError("x", status_code=503)))
        self.assertFalse(_is_retryable(NMTError("x", status_code=401)))
        self.assertIn(429, RETRYABLE_STATUS_CODES)
        self.assertGreater(MAX_RETRY_ATTEMPTS, 1)

    def test_is_retryable_unwraps_wrapped_connection_error(self) -> None:
        # openai 连接错误会被包装成 NMTError(status_code=None)，
        # 重试判断必须看原始 cause，否则最常见的网络抖动不触发重试。
        wrapped = NMTError("openai connection failed", status_code=None)
        wrapped.__cause__ = ConnectionError("temporary network blip")
        self.assertTrue(_is_retryable(wrapped))

    def test_is_retryable_unwraps_wrapped_timeout(self) -> None:
        wrapped = NMTError("openai timed out", status_code=None)
        wrapped.__cause__ = asyncio.TimeoutError()
        self.assertTrue(_is_retryable(wrapped))

    def test_is_retryable_does_not_unwrap_non_retryable_cause(self) -> None:
        wrapped = NMTError("openai auth failed", status_code=None)
        wrapped.__cause__ = ValueError("invalid api key")
        self.assertFalse(_is_retryable(wrapped))


class NMTServiceTranslationMemoryTests(unittest.IsolatedAsyncioTestCase):
    """V5.3 翻译记忆库集成测试：命中复用 + 翻译后写回。"""

    async def test_lookup_hit_reuses_translation_without_api_call(self) -> None:
        from services.translation_memory import TranslationMemoryService

        service = NMTService()
        service._engine = "openai"
        # 预置记忆库：完整命中（与 collect_translate_stream_tokens 的句子一致）
        tm = TranslationMemoryService(session_id="tm-test", similarity_threshold=0.82)
        tm.add("Good morning", "大家早上好", language_pair="en->zh-CN")
        service.attach_translation_memory(tm)

        # 若命中则不会触达上游，因此 client 故意不配置也会成功
        tokens = await collect_translate_stream_tokens(service)

        self.assertEqual(tokens, ["大家早上好", "<FINAL>"])

    async def test_lookup_miss_falls_through_to_api(self) -> None:
        from services.translation_memory import TranslationMemoryService

        service = NMTService()
        service._engine = "openai"
        service._client = FakeOpenAIClient([chunk_with_content("新译文")])
        tm = TranslationMemoryService(session_id="tm-test", similarity_threshold=0.82)
        tm.add("Good morning everyone", "大家早上好", language_pair="en->zh-CN")
        service.attach_translation_memory(tm)

        # 完全不同的句子：不命中，走 API
        tokens = await collect_translate_stream_tokens(service)

        self.assertEqual(tokens, ["新译文", "<FINAL>"])

    async def test_fuzzy_hit_reuses_for_similar_sentence(self) -> None:
        from services.translation_memory import TranslationMemoryService

        service = NMTService()
        service._engine = "openai"
        tm = TranslationMemoryService(session_id="tm-test", similarity_threshold=0.82)
        tm.add(
            "The Kubernetes cluster is running in production",
            "Kubernetes 集群已在生产环境运行",
            language_pair="en->zh-CN",
        )
        service.attach_translation_memory(tm)

        context = ContextWindow(session_id="tm-test", window_size=10)
        current = Segment(
            id="tm-1",
            text_asr="The Kubernetes cluster is running in production now",
            confidence=1.0,
        )
        tokens = [
            token
            async for token in service.translate_stream(context, current)
        ]

        self.assertEqual(tokens, ["Kubernetes 集群已在生产环境运行", "<FINAL>"])

    def test_record_translation_writes_to_tm(self) -> None:
        from services.translation_memory import TranslationMemoryService

        service = NMTService()
        tm = TranslationMemoryService(session_id="tm-test")
        service.attach_translation_memory(tm)

        segment = Segment(
            id="tm-2",
            text_asr="Hello world",
            confidence=1.0,
            source_language="en",
            target_language="zh-CN",
        )
        service.record_translation(segment, "你好世界")

        self.assertEqual(tm.size, 1)
        stats = tm.stats
        self.assertEqual(stats["written"], 1)
        # 再次翻译相同句子应命中记忆库
        match = tm.lookup("Hello world", language_pair="en->zh-CN")
        self.assertIsNotNone(match)
        if match is not None:
            self.assertEqual(match.translated, "你好世界")

    async def test_translation_memory_disabled_skips_lookup(self) -> None:
        from services.translation_memory import TranslationMemoryService

        original = settings.translation_memory_enabled
        settings.translation_memory_enabled = False
        try:
            service = NMTService()
            service._engine = "openai"
            tm = TranslationMemoryService(session_id="tm-test")
            tm.add("Good morning", "大家早上好", language_pair="en->zh-CN")
            service.attach_translation_memory(tm)

            # 禁用时命中也应返回 None，走 API（client 未配置会降级为原文透传）
            tokens = await collect_translate_stream_tokens(service)
            self.assertTrue(tokens[0].startswith("[未翻译]"))
        finally:
            settings.translation_memory_enabled = original


async def collect_tokens(service: NMTService) -> list[str]:
    context = ContextWindow(session_id="test-session", window_size=10)
    current = Segment(
        id="test-1",
        text_asr="Good morning.",
        confidence=1.0,
    )
    return [
        token
        async for token in service._translate_openai(context, current)
    ]


def chunk_with_choices(choices: list[object]) -> object:
    return SimpleNamespace(choices=choices)


def chunk_with_choice(choice: object) -> object:
    return chunk_with_choices([choice])


def chunk_with_content(content: str | None) -> object:
    return chunk_with_choice(SimpleNamespace(delta=SimpleNamespace(content=content)))


if __name__ == "__main__":
    unittest.main()
