"""
Provider client construction is isolated to this module. Nothing outside
model_gateway/ may import an LLM provider SDK (openai, anthropic,
google-generativeai, ...) directly — see docs/adr/0002-model-gateway-boundary.md.

Groq and OpenRouter both expose OpenAI-compatible chat-completions APIs, so
they're implemented as thin `openai.AsyncOpenAI` clients pointed at a
different base_url + api_key rather than adding new SDK dependencies (which
would also mean widening test_model_gateway_boundary.py's allow-list).

Anthropic remains a stub (no use_case_policy entry routes to it). OpenAI
itself is wired up but currently unused by any policy (no working key at
present) — kept in place so it's a one-line policy change to bring back.
"""

import os
from collections.abc import AsyncIterator
from enum import Enum

from google import genai
from openai import AsyncOpenAI


class Provider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    GROQ = "groq"
    OPENROUTER = "openrouter"


class ProviderClient:
    async def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError

    async def stream_complete(
        self, *, system_prompt: str, user_prompt: str
    ) -> AsyncIterator[str]:
        """Default fallback for providers without a true streaming
        implementation: yields the full completion once. Real streaming
        providers (OpenAI-compatible ones, Gemini below) override this."""
        yield await self.complete(system_prompt=system_prompt, user_prompt=user_prompt)

    async def complete_json(self, *, system_prompt: str, user_prompt: str) -> str:
        """Best-effort JSON-mode completion — providers below override this
        to actually request their native JSON/structured-output mode.
        Callers (gateway.py's run_structured) validate the result against a
        schema regardless, so this default (no enforcement) is safe: a
        provider with no JSON mode just relies on validation to catch a
        malformed response and retry, same as one that ignores its own
        JSON-mode flag."""
        return await self.complete(system_prompt=system_prompt, user_prompt=user_prompt)


class _OpenAICompatibleClient(ProviderClient):
    """Shared implementation for any provider that speaks the OpenAI
    chat-completions wire format — OpenAI itself, Groq, and OpenRouter today.
    Subclasses only need to construct the right `AsyncOpenAI` client."""

    def __init__(self, client: AsyncOpenAI, model: str, max_tokens: int = 2048) -> None:
        self._client = client
        self._model = model
        # Without an explicit cap, some providers (observed on OpenRouter)
        # default to the model's absolute max (e.g. 65536 for Claude Sonnet
        # 5), which needlessly inflates cost/latency and can fail outright
        # on a constrained account balance. None of our use cases need more
        # than a few paragraphs of output.
        self._max_tokens = max_tokens

    async def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=self._max_tokens,
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError(f"{self._model} completion returned no content")
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
            max_tokens=self._max_tokens,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    async def complete_json(self, *, system_prompt: str, user_prompt: str) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=self._max_tokens,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError(f"{self._model} JSON completion returned no content")
        return content


class OpenAIProviderClient(_OpenAICompatibleClient):
    def __init__(self, model: str = "gpt-4o-mini") -> None:
        super().__init__(AsyncOpenAI(), model)


class GroqProviderClient(_OpenAICompatibleClient):
    def __init__(self, model: str = "llama-3.3-70b-versatile") -> None:
        client = AsyncOpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=os.environ.get("GROQ_API_KEY"),
        )
        super().__init__(client, model)


class OpenRouterProviderClient(_OpenAICompatibleClient):
    def __init__(self, model: str = "anthropic/claude-sonnet-5") -> None:
        client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ.get("OPENROUTER_API_KEY"),
        )
        super().__init__(client, model)


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

    async def complete_json(self, *, system_prompt: str, user_prompt: str) -> str:
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=user_prompt,
            config={"system_instruction": system_prompt, "response_mime_type": "application/json"},
        )
        if not response.text:
            raise RuntimeError("Gemini JSON completion returned no content")
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


_CLIENT_FACTORIES = {
    Provider.OPENAI: OpenAIProviderClient,
    Provider.GEMINI: GeminiProviderClient,
    Provider.GROQ: GroqProviderClient,
    Provider.OPENROUTER: OpenRouterProviderClient,
}


def get_provider_client(provider: Provider, model: str | None = None) -> ProviderClient:
    """`model` lets a use_case_policy pick a specific model tier (e.g. a
    small vs large Groq model) without providers.py needing to know about
    per-use-case tiering — the policy table stays the single source of truth
    for "which model handles this," per the module's routing-auditability
    intent (see use_case_policy.py)."""
    factory = _CLIENT_FACTORIES.get(provider)
    if factory is None:
        return _UnimplementedProviderClient(provider)
    return factory(model) if model else factory()
