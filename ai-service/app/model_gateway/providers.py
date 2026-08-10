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

from __future__ import annotations

import asyncio
import json
import os
import re
import threading
from collections.abc import AsyncIterator
from enum import Enum
from typing import Any

from openai import AsyncOpenAI

from app.config import get_settings


class Provider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    GROQ = "groq"
    OPENROUTER = "openrouter"
    LIVEKIT_INFERENCE = "livekit_inference"
    MOCK = "mock"
    LOCAL = "local"


class ProviderClient:
    def __init__(self, provider: Provider | None = None) -> None:
        # Optional for audit/resume paths; voice clients may leave unset.
        self.provider = provider

    async def complete(
        self, *, system_prompt: str, user_prompt: str, max_tokens: int | None = None
    ) -> str:
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

    async def complete(
        self, *, system_prompt: str, user_prompt: str, max_tokens: int | None = None
    ) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens if max_tokens is not None else self._max_tokens,
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
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise KeyError("OPENAI_API_KEY environment variable is not set")
        super().__init__(AsyncOpenAI(api_key=api_key), model)


class GroqProviderClient(_OpenAICompatibleClient):
    def __init__(self, model: str = "llama-3.3-70b-versatile") -> None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise KeyError("GROQ_API_KEY environment variable is not set")
        client = AsyncOpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=api_key,
        )
        super().__init__(client, model)


class OpenRouterProviderClient(_OpenAICompatibleClient):
    def __init__(self, model: str = "anthropic/claude-sonnet-5") -> None:
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise KeyError("OPENROUTER_API_KEY environment variable is not set")
        client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        super().__init__(client, model)


class GeminiProviderClient(ProviderClient):
    def __init__(self, model: str = "gemini-flash-latest") -> None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise KeyError("GEMINI_API_KEY environment variable is not set")
        # Lazy: only pay this SDK's memory footprint in a process that
        # actually constructs a Gemini client (voice worker is OpenAI-only).
        from google import genai

        self._model = model
        self._client = genai.Client(api_key=api_key)

    async def complete(
        self, *, system_prompt: str, user_prompt: str, max_tokens: int | None = None
    ) -> str:
        config: dict = {"system_instruction": system_prompt}
        if max_tokens is not None:
            config["max_output_tokens"] = max_tokens
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=user_prompt,
            config=config,
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

    async def complete(
        self, *, system_prompt: str, user_prompt: str, max_tokens: int | None = None
    ) -> str:
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

    async def complete(
        self, *, system_prompt: str, user_prompt: str, max_tokens: int | None = None
    ) -> str:
        raise NotImplementedError(
            f"Provider '{self._provider.value}' is not wired up yet — "
            "no use_case_policy entry routes to it in this POC."
        )


class MockProviderClient(ProviderClient):
    """Free local stub for process testing — no network / credits."""

    def __init__(self, *, fallback_reason: str | None = None) -> None:
        super().__init__(Provider.MOCK)
        self.fallback_reason = fallback_reason

    async def complete(
        self, *, system_prompt: str, user_prompt: str, max_tokens: int | None = None
    ) -> str:
        body = user_prompt
        if "---" in user_prompt:
            parts = user_prompt.split("---")
            if len(parts) >= 2:
                body = parts[1]

        email_match = re.search(
            r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
            body,
        )
        phone_match = re.search(
            r"(?:\+?\d[\d\-\s().]{7,}\d)",
            body,
        )
        lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
        name = None
        for ln in lines[:12]:
            lower = ln.lower()
            if lower.startswith(("[truncated]", "resume", "{", "map resume")):
                continue
            if "@" in ln or re.search(r"\d{3,}", ln):
                continue
            if 2 <= len(ln.split()) <= 5 and len(ln) < 60:
                name = ln
                break

        summary = (
            "Mock extraction for local process testing "
            "(set LLM_MODE=gemini or openrouter for a real model)."
        )
        if self.fallback_reason:
            summary = self.fallback_reason

        skills: list[str] = []
        for i, ln in enumerate(lines):
            if re.match(r"(?i)^skills?\b", ln):
                # same line after colon, or following lines
                after = ln.split(":", 1)[1].strip() if ":" in ln else ""
                chunk = after
                if not chunk and i + 1 < len(lines):
                    chunk = lines[i + 1]
                for part in re.split(r"[,|/•;]", chunk):
                    skill = part.strip()
                    if 1 < len(skill) < 40:
                        skills.append(skill)
                skills = skills[:15]
                break

        payload = {
            "schema_version": "2.0",
            "contact": {
                "full_name": name,
                "email": email_match.group(0) if email_match else None,
                "phone": phone_match.group(0).strip() if phone_match else None,
                "location": None,
                "linkedin": None,
                "website": None,
                "github": None,
                "other_links": [],
            },
            "headline": None,
            "summary": summary,
            "experience": [],
            "education": [],
            "skills": skills,
            "skill_groups": {},
            "projects": [],
            "certifications": [],
            "languages": [],
            "awards": [],
            "publications": [],
            "volunteering": [],
            "interests": [],
            "additional_sections": [],
            "verification_topics": [],
        }
        return json.dumps(payload)


_local_lock = threading.Lock()
_local_tokenizer: Any = None
_local_model: Any = None
_local_model_id: str | None = None
_local_device: str | None = None


def _resolve_local_device(requested: str) -> str:
    import torch

    choice = (requested or "auto").strip().lower()
    if choice == "auto":
        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
        return "cpu"
    if choice in ("mps", "cuda", "cpu"):
        if choice == "mps" and not torch.backends.mps.is_available():
            return "cpu"
        if choice == "cuda" and not torch.cuda.is_available():
            return "cpu"
        return choice
    return "cpu"


def _ensure_local_model(model_id: str, device_pref: str) -> tuple[Any, Any, str]:
    """Lazy-load tokenizer + causal LM (thread-safe singleton)."""
    global _local_tokenizer, _local_model, _local_model_id, _local_device

    with _local_lock:
        device = _resolve_local_device(device_pref)
        if (
            _local_model is not None
            and _local_tokenizer is not None
            and _local_model_id == model_id
            and _local_device == device
        ):
            return _local_tokenizer, _local_model, device

        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
        dtype = torch.float16 if device in ("mps", "cuda") else torch.float32
        try:
            model = AutoModelForCausalLM.from_pretrained(
                model_id,
                trust_remote_code=True,
                dtype=dtype,
            )
        except TypeError:
            # Older transformers used torch_dtype=
            model = AutoModelForCausalLM.from_pretrained(
                model_id,
                trust_remote_code=True,
                torch_dtype=dtype,
            )
        model.to(device)
        model.eval()

        _local_tokenizer = tokenizer
        _local_model = model
        _local_model_id = model_id
        _local_device = device
        return tokenizer, model, device


def _build_local_prompt(tokenizer: Any, system_prompt: str, user_prompt: str) -> str:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    if hasattr(tokenizer, "apply_chat_template") and getattr(
        tokenizer, "chat_template", None
    ):
        return tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
    return f"System:\n{system_prompt}\n\nUser:\n{user_prompt}\n\nAssistant:\n"


def _generate_local_sync(*, system_prompt: str, user_prompt: str) -> str:
    import torch

    get_settings.cache_clear()
    settings = get_settings()
    model_id = (settings.local_llm_model or "Qwen/Qwen2.5-0.5B-Instruct").strip()
    tokenizer, model, device = _ensure_local_model(
        model_id,
        settings.local_llm_device,
    )

    prompt = _build_local_prompt(tokenizer, system_prompt, user_prompt)
    inputs = tokenizer(prompt, return_tensors="pt")
    inputs = {k: v.to(device) for k, v in inputs.items()}
    prompt_len = int(inputs["input_ids"].shape[-1])

    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=settings.local_llm_max_new_tokens,
            do_sample=False,
            pad_token_id=getattr(tokenizer, "eos_token_id", None),
        )

    generated = output_ids[0][prompt_len:]
    text = tokenizer.decode(generated, skip_special_tokens=True).strip()
    if not text:
        raise RuntimeError("Local transformers model returned an empty completion")
    return text


class LocalTransformersProviderClient(ProviderClient):
    """Local instruct model via transformers + torch (Mac MPS / CUDA / CPU)."""

    def __init__(self) -> None:
        super().__init__(Provider.LOCAL)

    async def complete(
        self, *, system_prompt: str, user_prompt: str, max_tokens: int | None = None
    ) -> str:
        # max_tokens intentionally unused here — local generation budget is
        # local_llm_max_new_tokens (a separate setting; the two aren't
        # comparable units the way provider max_tokens is).
        return await asyncio.to_thread(
            _generate_local_sync,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )


def is_llm_quota_error(exc: BaseException) -> bool:
    """True for Gemini/OpenAI-compatible rate-limit or quota exhaustion errors."""
    text = f"{type(exc).__name__} {exc}".lower()
    markers = (
        "429",
        "quota",
        "rate limit",
        "rate_limit",
        "resource_exhausted",
        "exceeded your current quota",
        "insufficient_quota",
    )
    return any(m in text for m in markers)




_CLIENT_FACTORIES = {
    Provider.OPENAI: OpenAIProviderClient,
    Provider.GEMINI: GeminiProviderClient,
    Provider.GROQ: GroqProviderClient,
    Provider.OPENROUTER: OpenRouterProviderClient,
    Provider.LIVEKIT_INFERENCE: LiveKitInferenceProviderClient,
}


def get_provider_client(provider: Provider, model: str | None = None) -> ProviderClient:
    """`model` lets a use_case_policy pick a specific model tier (e.g. a
    small vs large Groq model) without providers.py needing to know about
    per-use-case tiering — the policy table stays the single source of truth
    for "which model handles this," per the module's routing-auditability
    intent (see use_case_policy.py).

    When Settings.llm_mode is mock/local/gemini/openrouter, resume extractor
    paths may force that mode regardless of the requested provider.
    """
    get_settings.cache_clear()
    settings = get_settings()
    mode = (settings.llm_mode or "").strip().lower()
    if mode == "mock" or provider == Provider.MOCK:
        return MockProviderClient()
    if mode == "local" or provider == Provider.LOCAL:
        return LocalTransformersProviderClient()

    factory = _CLIENT_FACTORIES.get(provider)
    if factory is None:
        return _UnimplementedProviderClient(provider)
    return factory(model) if model else factory()
