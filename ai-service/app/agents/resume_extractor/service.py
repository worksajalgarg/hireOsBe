"""Orchestration helpers that call the model gateway (no provider SDKs)."""

from __future__ import annotations

import json
import re
from typing import Any

from app.config import get_settings
from app.model_gateway.gateway import model_gateway

from .prompts import SYSTEM_PROMPT, build_user_prompt
from .schemas import ResumeJSON

# Keep LLM input small so completion fits low OpenRouter max_tokens budgets.
LLM_RESUME_MAX_CHARS = 8_000


def _strip_json_fences(raw: str) -> str:
    text = raw.strip()
    fence = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", text, re.IGNORECASE)
    if fence:
        return fence.group(1).strip()
    return text


def _repair_truncated_json(text: str) -> str:
    """Best-effort close of truncated LLM JSON (unterminated strings / braces)."""
    s = text.strip()
    if not s:
        return s

    in_string = False
    escape = False
    stack: list[str] = []
    for ch in s:
        if escape:
            escape = False
            continue
        if in_string:
            if ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if stack and stack[-1] == ch:
                stack.pop()

    if in_string:
        s += '"'

    s = re.sub(r",\s*$", "", s)
    # Drop a dangling key without value: `"foo":` or `"foo`
    s = re.sub(r',?\s*"[^"]*"\s*:\s*$', "", s)
    s = re.sub(r",\s*$", "", s)

    # Recompute stack after edits
    in_string = False
    escape = False
    stack = []
    for ch in s:
        if escape:
            escape = False
            continue
        if in_string:
            if ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if stack and stack[-1] == ch:
                stack.pop()

    if in_string:
        s += '"'
    while stack:
        s += stack.pop()
    return s


def _parse_llm_json(raw: str) -> dict[str, Any]:
    cleaned = _strip_json_fences(raw)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        repaired = _repair_truncated_json(cleaned)
        try:
            parsed = json.loads(repaired)
            cleaned = repaired
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"LLM returned incomplete JSON (likely hit max_tokens). "
                f"Raise OPENAI_MAX_TOKENS or add OpenRouter credits. Parse error: {exc}"
            ) from exc

    if not isinstance(parsed, dict):
        raise ValueError("LLM response is not a JSON object")
    return parsed


async def extract_resume_json(normalized_text: str) -> tuple[str, dict[str, Any]]:
    """Run LLM extraction and return (raw_text, parsed_dict)."""
    get_settings.cache_clear()
    settings = get_settings()
    # Prefer shorter input when completion budget is tight.
    max_chars = LLM_RESUME_MAX_CHARS
    if settings.openai_max_tokens <= 768:
        max_chars = 6_000
    clipped = normalized_text[:max_chars]
    if len(normalized_text) > max_chars:
        clipped = clipped.rstrip() + "\n\n[truncated]"

    raw = await model_gateway.run(
        use_case="resume_parsing",
        system_prompt=SYSTEM_PROMPT,
        user_prompt=build_user_prompt(clipped),
    )
    parsed = _parse_llm_json(raw)
    return raw, parsed


def validate_resume_payload(payload: dict[str, Any]) -> ResumeJSON:
    return ResumeJSON.model_validate(payload)
