"""
Provider client construction is isolated to this module. Nothing outside
model_gateway/ may import an LLM provider SDK (openai, anthropic,
google-generativeai, ...) directly — see docs/adr/0002-model-gateway-boundary.md.

Anthropic/Gemini remain stubs (no use_case_policy entry routes to them yet).
OpenAI is wired up for real, since it's the first policy (`voice_interview_turn`)
that actually needs a live completion.
"""

import os
from collections.abc import AsyncIterator
from enum import Enum

import openai
from google import genai


class Provider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


class ProviderClient:
    async def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError

    async def stream_complete(
        self, *, system_prompt: str, user_prompt: str
    ) -> AsyncIterator[str]:
        """Default fallback for providers without a true streaming
        implementation: yields the full completion once. Real streaming
        providers (OpenAI, Gemini below) override this."""
        yield await self.complete(system_prompt=system_prompt, user_prompt=user_prompt)


class OpenAIProviderClient(ProviderClient):
    def __init__(self, model: str = "gpt-4o-mini") -> None:
        self._model = model
        self._client = openai.AsyncOpenAI()

    async def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("OpenAI completion returned no content")
        return content

    async def stream_complete(
        self, *, system_prompt: str, user_prompt: str
    ) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


class GeminiProviderClient(ProviderClient):
    def __init__(self, model: str = "gemini-flash-latest") -> None:
        self._model = model
        self._client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

    async def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=user_prompt,
            config={"system_instruction": system_prompt},
        )
        if not response.text:
            raise RuntimeError("Gemini completion returned no content")
        return response.text

    async def stream_complete(
        self, *, system_prompt: str, user_prompt: str
    ) -> AsyncIterator[str]:
        stream = await self._client.aio.models.generate_content_stream(
            model=self._model,
            contents=user_prompt,
            config={"system_instruction": system_prompt},
        )
        async for chunk in stream:
            if chunk.text:
                yield chunk.text


class _UnimplementedProviderClient(ProviderClient):
    def __init__(self, provider: Provider) -> None:
        self._provider = provider

    async def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError(
            f"Provider '{self._provider.value}' is not wired up yet — "
            "no use_case_policy entry routes to it in this POC."
        )


def get_provider_client(provider: Provider) -> ProviderClient:
    if provider is Provider.OPENAI:
        return OpenAIProviderClient()
    if provider is Provider.GEMINI:
        return GeminiProviderClient()
    return _UnimplementedProviderClient(provider)
