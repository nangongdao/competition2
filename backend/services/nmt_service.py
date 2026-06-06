"""NMT service backed by LLM APIs."""

from __future__ import annotations

from typing import AsyncIterator

from loguru import logger

from core.config import settings
from core.exceptions import NMTError
from models.segment import ContextWindow, Segment


class NMTService:
    SYSTEM_PROMPT = """You are a real-time interpreter translating English to Chinese.

Rules:
1. Translate naturally and fluently into Simplified Chinese
2. Preserve technical terms, proper nouns, and brand names in their original form
3. Maintain the speaker's tone consistently
4. Use context from previous sentences to resolve ambiguities
5. Output ONLY the Chinese translation, no explanations
6. Keep the translation concise and close to the original sentence length
7. For incomplete sentences, translate only what is available
"""

    def __init__(self) -> None:
        self._engine = settings.nmt_engine
        self._client = None

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
        if self._engine == "claude":
            async for token in self._translate_claude(context, current):
                yield token
            return
        if self._engine == "openai":
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

            context_text = context.to_context_text(max_sentences=settings.context_window_size)
            user_message = f"""Previous context (for reference only, already translated):
---
{context_text}
---

Translate this sentence from English to Chinese:
"{current.text_asr}"

Translation:"""

            async with self._client.messages.stream(
                model=settings.nmt_model,
                max_tokens=1024,
                system=self.SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            ) as stream:
                async for text in stream.text_stream:
                    yield text

            yield "<FINAL>"
        except anthropic.APIError as exc:
            logger.error("Claude API error: {}", exc)
            raise NMTError(f"Claude translation failed: {exc}")

    async def _translate_openai(
        self,
        context: ContextWindow,
        current: Segment,
    ) -> AsyncIterator[str]:
        try:
            context_text = context.to_context_text(max_sentences=settings.context_window_size)
            messages = [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"""Previous context (for reference only):
---
{context_text}
---

Translate this sentence from English to Chinese:
"{current.text_asr}"

Translation:""",
                },
            ]

            stream = await self._client.chat.completions.create(
                model=settings.nmt_model,
                messages=messages,
                max_tokens=1024,
                stream=True,
            )

            async for chunk in stream:
                token = chunk.choices[0].delta.content
                if token:
                    yield token

            yield "<FINAL>"
        except Exception as exc:
            logger.error("OpenAI API error: {}", exc)
            raise NMTError(f"OpenAI translation failed: {exc}")

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
            raise NMTError(f"Claude completion failed: {exc}")

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
            raise NMTError(f"OpenAI completion failed: {exc}")

    async def shutdown(self) -> None:
        self._client = None
        logger.info("NMT service shut down")
