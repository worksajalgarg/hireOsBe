"""
Provider client construction is isolated to this module. Nothing outside
model_gateway/ may import an LLM provider SDK (openai, anthropic,
google-generativeai, ...) directly — see docs/adr/0002-model-gateway-boundary.md.

Groq and OpenRouter both expose OpenAI-compatible chat-completions APIs, so
they're implemented as thin `openai.AsyncOpenAI` clients pointed at a
different base_url + api_key rather than adding new SDK dependencies (which
would also mean widening test_model_gateway_boundary.py's allow-list).

LiveKit Inference (`LIVEKIT_INFERENCE` provider): routes LLM calls through
LiveKit Cloud Inference using `livekit.agents.inference.LLM`. No separate
vendor API key needed — authenticated by `LIVEKIT_API_KEY`/`LIVEKIT_API_SECRET`
already required by the worker. Only used when `VOICE_PROVIDER=livekit_inference`;
gateway.py's `set_livekit_inference_mode()` replaces voice use-case chains with
pure `livekit_inference` tiers in that mode.

Anthropic remains a stub (no use_case_policy entry routes to it). OpenAI
itself is wired up but currently unused by any policy (no working key at
present) — kept in place so it's a one-line policy change to bring back.
"""

import os
from collections.abc import AsyncIterator
from enum import Enum

from openai import AsyncOpenAI


class Provider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    GROQ = "groq"
    OPENROUTER = "openrouter"
    LIVEKIT_INFERENCE = "livekit_inference"


def _max_tokens_kwarg(max_tokens: int | None) -> dict[str, int]:
    """None means "use the client's own default" — only pass max_tokens
    through when a policy tier actually overrides it, so _OpenAICompatibleClient's
    default stays the single source of truth for the un-overridden case."""
    return {"max_tokens": max_tokens} if max_tokens is not None else {}


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
    def __init__(self, model: str = "gpt-4o-mini", max_tokens: int | None = None) -> None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise KeyError("OPENAI_API_KEY environment variable is not set")
        super().__init__(AsyncOpenAI(api_key=api_key), model, **_max_tokens_kwarg(max_tokens))


class GroqProviderClient(_OpenAICompatibleClient):
    def __init__(
        self, model: str = "llama-3.3-70b-versatile", max_tokens: int | None = None
    ) -> None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise KeyError("GROQ_API_KEY environment variable is not set")
        client = AsyncOpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=api_key,
        )
        super().__init__(client, model, **_max_tokens_kwarg(max_tokens))


class OpenRouterProviderClient(_OpenAICompatibleClient):
    def __init__(
        self, model: str = "anthropic/claude-sonnet-5", max_tokens: int | None = None
    ) -> None:
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise KeyError("OPENROUTER_API_KEY environment variable is not set")
        client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        super().__init__(client, model, **_max_tokens_kwarg(max_tokens))


class GeminiProviderClient(ProviderClient):
    def __init__(self, model: str = "gemini-flash-latest", max_tokens: int | None = None) -> None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise KeyError("GEMINI_API_KEY environment variable is not set")
        # Lazy: only pay this SDK's memory footprint in a process that
        # actually constructs a Gemini client (voice worker is OpenAI-only).
        from google import genai

        self._model = model
        self._max_output_tokens = max_tokens
        self._client = genai.Client(api_key=api_key)

    async def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        config: dict[str, object] = {"system_instruction": system_prompt}
        if self._max_output_tokens is not None:
            config["max_output_tokens"] = self._max_output_tokens
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=user_prompt,
            config=config,
        )
        if not response.text:
            raise RuntimeError("Gemini completion returned no content")
        return response.text

    async def complete_json(self, *, system_prompt: str, user_prompt: str) -> str:
        config: dict[str, object] = {
            "system_instruction": system_prompt,
            "response_mime_type": "application/json",
        }
        if self._max_output_tokens is not None:
            config["max_output_tokens"] = self._max_output_tokens
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=user_prompt,
            config=config,
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


class LiveKitInferenceProviderClient(ProviderClient):
    """Routes LLM calls through LiveKit Cloud Inference using the same
    LIVEKIT_API_KEY/LIVEKIT_API_SECRET already required for STT/TTS.
    No separate vendor API key needed. Only constructed when
    VOICE_PROVIDER=livekit_inference (see gateway.py's
    set_livekit_inference_mode()).

    `inference.LLM` uses the livekit.agents ChatContext / ChatMessage
    convention internally; we adapt our (system_prompt, user_prompt) interface
    to that shape here so the rest of the gateway layer needs no changes.
    """

    def __init__(self, model: str = "google/gemini-2.5-flash-lite") -> None:
        if not os.environ.get("LIVEKIT_API_KEY"):
            raise KeyError("LIVEKIT_API_KEY not set — LiveKit Inference LLM unavailable")
        from livekit.agents import inference  # lazy: avoids import error if package absent
        self._llm = inference.LLM(model=model)
        self._model = model

    def _build_chat_ctx(self, system_prompt: str, user_prompt: str):
        from livekit.agents.llm import ChatContext
        ctx = ChatContext()
        ctx.add_message(role="system", content=system_prompt)
        ctx.add_message(role="user", content=user_prompt)
        return ctx

    async def stream_complete(
        self, *, system_prompt: str, user_prompt: str
    ) -> AsyncIterator[str]:
        ctx = self._build_chat_ctx(system_prompt, user_prompt)
        async for chunk in self._llm.chat(chat_ctx=ctx):
            delta = getattr(chunk, "delta", None)
            content = getattr(delta, "content", None) if delta else None
            if content:
                yield content

    async def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        parts = [c async for c in self.stream_complete(
            system_prompt=system_prompt, user_prompt=user_prompt
        )]
        result = "".join(parts)
        if not result:
            raise RuntimeError(f"LiveKit Inference ({self._model}) returned no content")
        return result


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
    Provider.LIVEKIT_INFERENCE: LiveKitInferenceProviderClient,
}


_SUPPORTS_MAX_TOKENS = {
    Provider.OPENAI,
    Provider.GEMINI,
    Provider.GROQ,
    Provider.OPENROUTER,
}


def get_provider_client(
    provider: Provider, model: str | None = None, max_tokens: int | None = None
) -> ProviderClient:
    """`model` lets a use_case_policy pick a specific model tier (e.g. a
    small vs large Groq model) without providers.py needing to know about
    per-use-case tiering — the policy table stays the single source of truth
    for "which model handles this," per the module's routing-auditability
    intent (see use_case_policy.py). `max_tokens` is the same idea for a
    tier's output budget — only the OpenAI-compatible clients and Gemini
    accept it; LiveKit Inference has no equivalent knob, so it's silently
    ignored there rather than erroring on an unused override."""
    factory = _CLIENT_FACTORIES.get(provider)
    if factory is None:
        return _UnimplementedProviderClient(provider)
    kwargs: dict[str, object] = {}
    if model:
        kwargs["model"] = model
    if max_tokens is not None and provider in _SUPPORTS_MAX_TOKENS:
        kwargs["max_tokens"] = max_tokens
    return factory(**kwargs)
