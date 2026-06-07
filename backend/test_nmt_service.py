from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import unittest


BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from models.segment import ContextWindow, Segment
from services.nmt_service import NMTService


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
