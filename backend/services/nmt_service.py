"""NMT service backed by LLM APIs."""

from __future__ import annotations

import asyncio
import random
from typing import AsyncIterator

from loguru import logger

from core.config import settings
from core.exceptions import NMTError
from models.segment import ContextWindow, Segment
from services.glossary import GlossaryEntry, build_glossary_prompt
from services.language_config import source_language_label, target_language_label


#: 可重试的上游错误类型（限流与服务端错误）
RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})
MAX_RETRY_ATTEMPTS = 3
BASE_BACKOFF_SECONDS = 0.4


def _is_retryable(exc: Exception) -> bool:
    """判断异常是否值得重试。

    Args:
        exc: 上游调用抛出的异常。

    Returns:
        限流/超时/5xx 返回 True；鉴权失败等永久错误返回 False。
    """
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status in RETRYABLE_STATUS_CODES
    if isinstance(exc, (asyncio.TimeoutError, ConnectionError)):
        return True

    # 连接错误/超时常被包装成 NMTError（status_code=None），
    # 检查原始 cause（httpx/openai 异常）避免漏判最常见的网络抖动。
    cause = exc.__cause__
    if isinstance(cause, (asyncio.TimeoutError, ConnectionError)):
        return True
    cause_status = getattr(cause, "status_code", None)
    if isinstance(cause_status, int):
        return cause_status in RETRYABLE_STATUS_CODES
    return False


class NMTService:
    RULES_PROMPT = """Rules:
1. Translate naturally and fluently into the target language
2. Preserve technical terms, proper nouns, and brand names in their original form
3. Maintain the speaker's tone consistently
4. Use context from previous sentences to resolve ambiguities
5. Output ONLY the target-language translation, no explanations
6. Keep the translation concise and close to the original sentence length
7. For incomplete sentences, translate only what is available
"""

    SYSTEM_PROMPT = f"""You are a real-time interpreter translating English speech to Simplified Chinese.

{RULES_PROMPT}"""

    def __init__(self) -> None:
        self._engine = settings.nmt_engine
        self._client = None
        self._glossary: list[GlossaryEntry] = []

    def set_glossary(self, entries: list[GlossaryEntry]) -> None:
        """设置会话术语表（领域自适应）。

        Args:
            entries: 术语表条目列表。
        """
        self._glossary = list(entries)
        logger.info("Glossary updated with {} entries", len(self._glossary))

    async def initialize(self) -> None:
        if self._engine == "claude":
            await self._init_claude()
            return
        if self._engine == "openai":
            await self._init_openai()
            return
        raise NMTError(f"Unknown NMT engine: {self._engine}")

    async def _init_claude(self) -> None:
        try:
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
            logger.info("Anthropic client initialized")
        except Exception as exc:
            logger.error("Failed to init Anthropic client: {}", exc)
            raise NMTError(f"Anthropic init failed: {exc}")

    async def _init_openai(self) -> None:
        try:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
            )
            logger.info("OpenAI client initialized")
        except Exception as exc:
            logger.error("Failed to init OpenAI client: {}", exc)
            raise NMTError(f"OpenAI init failed: {exc}")

    async def translate_stream(
        self,
        context: ContextWindow,
        current: Segment,
    ) -> AsyncIterator[str]:
        """带指数退避重试的翻译调用。

        失败时不中断会话，而是降级为原文透传，保证字幕不断流 ——
        同传场景下"降级的字幕"远好于"没有字幕"。
        """
        if self._engine not in {"claude", "openai"}:
            raise NMTError(f"Unknown NMT engine: {self._engine}")

        last_error: Exception | None = None
        attempts = 0
        for attempt in range(MAX_RETRY_ATTEMPTS):
            attempts += 1
            emitted_any = False
            try:
                stream = self._translate_stream_once(context, current)
                async for token in stream:
                    if token != "<FINAL>":
                        emitted_any = True
                    yield token
                return
            except Exception as exc:
                last_error = exc
                # 已向客户端吐出部分 token 时不再重试，避免字幕重复拼接。
                if emitted_any or not _is_retryable(exc) or attempt == MAX_RETRY_ATTEMPTS - 1:
                    break

                delay = BASE_BACKOFF_SECONDS * (2 ** attempt)
                jitter = random.uniform(0, delay * 0.3)
                logger.warning(
                    "Translation attempt {}/{} failed ({}), retrying in {:.2f}s",
                    attempt + 1, MAX_RETRY_ATTEMPTS, exc, delay + jitter,
                )
                await asyncio.sleep(delay + jitter)

        # 全部重试失败：降级为原文透传而非中断会话
        logger.error("Translation failed after {} attempts: {}", attempts, last_error)
        yield f"[未翻译] {current.text_asr}"
        yield "<FINAL>"

    async def _translate_stream_once(
        self,
        context: ContextWindow,
        current: Segment,
    ) -> AsyncIterator[str]:
        """按所选引擎执行单次翻译流调用。"""
        if self._engine == "claude":
            async for token in self._translate_claude(context, current):
                yield token
            return
        async for token in self._translate_openai(context, current):
            yield token

    async def complete_text(self, prompt: str, *, system_prompt: str) -> str:
        if self._engine == "claude":
            return await self._complete_claude(prompt, system_prompt)
        if self._engine == "openai":
            return await self._complete_openai(prompt, system_prompt)
        raise NMTError(f"Unknown NMT engine: {self._engine}")

    async def _translate_claude(
        self,
        context: ContextWindow,
        current: Segment,
    ) -> AsyncIterator[str]:
        try:
            import anthropic

            user_message = self._build_translation_prompt(context, current)

            async with self._client.messages.stream(
                model=settings.nmt_model,
                max_tokens=1024,
                system=self._build_system_prompt(current),
                messages=[{"role": "user", "content": user_message}],
            ) as stream:
                async for text in stream.text_stream:
                    yield text

            yield "<FINAL>"
        except anthropic.APIError as exc:
            logger.error("Claude API error: {}", exc)
            raise NMTError(
                f"Claude translation failed: {exc}",
                status_code=getattr(exc, "status_code", None),
            ) from exc

    async def _translate_openai(
        self,
        context: ContextWindow,
        current: Segment,
    ) -> AsyncIterator[str]:
        try:
            messages = [
                {"role": "system", "content": self._build_system_prompt(current)},
                {
                    "role": "user",
                    "content": self._build_translation_prompt(context, current),
                },
            ]

            stream = await self._client.chat.completions.create(
                model=settings.nmt_model,
                messages=messages,
                max_tokens=1024,
                stream=True,
            )

            async for chunk in stream:
                if not chunk.choices:
                    continue

                delta = getattr(chunk.choices[0], "delta", None)
                token = getattr(delta, "content", None)
                if token:
                    yield token

            yield "<FINAL>"
        except Exception as exc:
            logger.error("OpenAI API error: {}", exc)
            raise NMTError(
                f"OpenAI translation failed: {exc}",
                status_code=getattr(exc, "status_code", None),
            ) from exc

    async def _complete_claude(self, prompt: str, system_prompt: str) -> str:
        try:
            response = await self._client.messages.create(
                model=settings.nmt_model,
                max_tokens=512,
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )
            parts: list[str] = []
            for block in response.content:
                text = getattr(block, "text", "")
                if text:
                    parts.append(text)
            return "".join(parts).strip()
        except Exception as exc:
            logger.error("Claude completion error: {}", exc)
            raise NMTError(
                f"Claude completion failed: {exc}",
                status_code=getattr(exc, "status_code", None),
            ) from exc

    async def _complete_openai(self, prompt: str, system_prompt: str) -> str:
        try:
            response = await self._client.chat.completions.create(
                model=settings.nmt_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=512,
                stream=False,
            )
            content = response.choices[0].message.content
            return content.strip() if content else ""
        except Exception as exc:
            logger.error("OpenAI completion error: {}", exc)
            raise NMTError(
                f"OpenAI completion failed: {exc}",
                status_code=getattr(exc, "status_code", None),
            ) from exc

    def _build_system_prompt(self, current: Segment) -> str:
        source_label = source_language_label(current.source_language)
        target_label = target_language_label(current.target_language)
        return f"""You are a real-time interpreter translating {source_label} speech to {target_label}.

{self.RULES_PROMPT}"""

    def _build_translation_prompt(self, context: ContextWindow, current: Segment) -> str:
        context_text = context.to_context_text(
            max_sentences=settings.context_window_size,
            recent_sentences=settings.context_recent_sentences,
            older_max_chars=settings.context_older_max_chars,
        )
        source_label = source_language_label(current.source_language)
        target_label = target_language_label(current.target_language)

        # 只注入本句命中的术语约束，避免 prompt 膨胀
        glossary_prompt = build_glossary_prompt(self._glossary, current.text_asr)
        glossary_block = f"\n{glossary_prompt}" if glossary_prompt else ""

        return f"""Previous context (for reference only, already translated):
---
{context_text}
---

Translate this sentence from {source_label} to {target_label}:
"{current.text_asr}"
{glossary_block}
Translation:"""

    async def shutdown(self) -> None:
        self._client = None
        logger.info("NMT service shut down")
