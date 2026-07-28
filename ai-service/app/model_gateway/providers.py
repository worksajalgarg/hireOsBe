"""
Provider client construction is isolated to this module. Nothing outside
model_gateway/ may import an LLM provider SDK (openai, anthropic,
google-generativeai, ...) directly — see docs/adr/0002-model-gateway-boundary.md.
"""

from __future__ import annotations

import json
import os
import re
from enum import Enum

from app.config import get_settings


class Provider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    MOCK = "mock"


class ProviderClient:
    def __init__(self, provider: Provider):
        self.provider = provider

    async def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError(
            f"Provider '{self.provider.value}' is not wired up yet — "
            "Sprint 1 scaffold only defines the gateway boundary."
        )


class MockProviderClient(ProviderClient):
    """Free local stub for process testing — no network / credits."""

    def __init__(self, *, fallback_reason: str | None = None) -> None:
        super().__init__(Provider.MOCK)
        self.fallback_reason = fallback_reason

    async def complete(self, *, system_prompt: str, user_prompt: str) -> str:
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
            "contact": {
                "full_name": name,
                "email": email_match.group(0) if email_match else None,
                "phone": phone_match.group(0).strip() if phone_match else None,
                "location": None,
                "linkedin": None,
                "website": None,
            },
            "summary": summary,
            "experience": [],
            "education": [],
            "skills": skills,
            "certifications": [],
            "languages": [],
        }
        return json.dumps(payload)


class OpenAIProviderClient(ProviderClient):
    def __init__(self) -> None:
        super().__init__(Provider.OPENAI)

    async def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        from openai import AsyncOpenAI

        get_settings.cache_clear()
        settings = get_settings()
        api_key = settings.openai_api_key or os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Add your OpenRouter (or OpenAI) key "
                "to ai-service/.env"
            )

        client_kwargs: dict[str, object] = {"api_key": api_key}
        base_url = (settings.openai_base_url or "").strip()
        if base_url:
            client_kwargs["base_url"] = base_url

        client = AsyncOpenAI(**client_kwargs)
        response = await client.chat.completions.create(
            model=settings.openai_model,
            temperature=0,
            max_tokens=settings.openai_max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("OpenAI returned an empty completion")
        return content


class GeminiProviderClient(ProviderClient):
    def __init__(self) -> None:
        super().__init__(Provider.GEMINI)

    async def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        import google.generativeai as genai

        get_settings.cache_clear()
        settings = get_settings()
        api_key = settings.gemini_api_key or os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Add it to ai-service/.env "
                "(Google AI Studio key)"
            )

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name=settings.gemini_model,
            system_instruction=system_prompt,
            generation_config={
                "temperature": 0,
                "max_output_tokens": settings.openai_max_tokens,
                "response_mime_type": "application/json",
            },
        )
        response = await model.generate_content_async(user_prompt)
        content = getattr(response, "text", None)
        if not content:
            raise RuntimeError("Gemini returned an empty completion")
        return content


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


def get_provider_client(provider: Provider) -> ProviderClient:
    get_settings.cache_clear()
    settings = get_settings()
    mode = (settings.llm_mode or "mock").strip().lower()
    if mode == "mock":
        return MockProviderClient()
    if mode == "gemini" or provider == Provider.GEMINI:
        return GeminiProviderClient()
    if mode in ("openrouter", "openai") or provider == Provider.OPENAI:
        return OpenAIProviderClient()
    if provider == Provider.OPENAI:
        return OpenAIProviderClient()
    return ProviderClient(provider)
