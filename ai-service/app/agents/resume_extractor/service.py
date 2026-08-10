"""Grounded LLM extraction, strict validation, and deterministic chunk merging."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.config import get_settings
from app.model_gateway.gateway import GatewayResult, current_model_name, model_gateway

from .model_limits import (
    is_context_length_error,
    max_output_tokens_for,
    safe_chunk_chars,
)
from .prompts import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_correction_prompt,
    build_user_prompt,
)
from .schemas import ExtractionMetadata, ResumeJSON

# Settings.openai_max_tokens defaults to 512 (deliberately low for other,
# smaller use cases — see config.py's comment). ResumeJSON's real shape
# (experience/education/skills/projects/certifications/awards/publications/
# etc., each item carrying an evidence quote) needs much more room —
# confirmed in practice: 512 produced an empty completion on a real resume,
# which surfaces as a confusing "invalid JSON" error rather than an obvious
# token-budget one.
#
# Floor only. The real budget comes from max_output_tokens_for(model) — a flat
# 4096 truncated a dense but ordinary resume mid-JSON, and since the schema is
# emitted in a fixed field order, the correction pass could only rebuild the
# surviving prefix and filled every later section (projects, certifications,
# awards, publications, volunteering, languages) with [].
_RESUME_EXTRACTION_MAX_TOKENS = 4096


@dataclass(frozen=True)
class ExtractionResult:
    resume: ResumeJSON
    raw_json: str
    provider: str
    model_name: str
    fallback_used: bool
    chunk_count: int


def _strip_json_fences(raw: str) -> str:
    text = raw.strip()
    fence = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", text, re.IGNORECASE)
    return fence.group(1).strip() if fence else text


def _parse_json_object(raw: str) -> dict[str, Any]:
    """Parse exact JSON. Incomplete model output must never become a partial success."""
    try:
        parsed = json.loads(_strip_json_fences(raw))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model returned invalid or incomplete JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Model response is not a JSON object")
    return parsed


def split_resume_text(text: str, *, max_chars: int, max_chunks: int) -> list[str]:
    """Split on paragraphs where possible while preserving the entire source."""
    paragraphs = [part.strip() for part in re.split(r"\n{2,}", text) if part.strip()]
    chunks: list[str] = []
    current = ""

    def append_piece(piece: str) -> None:
        nonlocal current
        candidate = f"{current}\n\n{piece}".strip() if current else piece
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = piece
        else:
            current = candidate

    for paragraph in paragraphs:
        if len(paragraph) <= max_chars:
            append_piece(paragraph)
            continue
        # Very large OCR paragraphs are split without dropping characters.
        if current:
            chunks.append(current)
            current = ""
        for start in range(0, len(paragraph), max_chars):
            chunks.append(paragraph[start : start + max_chars])

    if current:
        chunks.append(current)
    if not chunks and text.strip():
        chunks = [text.strip()]
    if len(chunks) > max_chunks:
        raise ValueError(
            f"Resume needs {len(chunks)} model chunks, exceeding configured limit "
            f"of {max_chunks}. Increase RESUME_LLM_MAX_CHUNKS."
        )
    return chunks


async def _extract_valid_chunk(
    chunk: str, *, chunk_index: int, chunk_count: int, max_output_tokens: int
) -> tuple[ResumeJSON, GatewayResult]:
    prompt = build_user_prompt(chunk, chunk_index=chunk_index, chunk_count=chunk_count)
    try:
        result = await model_gateway.run_detailed(
            use_case="resume_parsing",
            system_prompt=SYSTEM_PROMPT,
            user_prompt=prompt,
            max_tokens=max_output_tokens,
        )
    except Exception as exc:
        if is_context_length_error(exc) and len(chunk) > 2000:
            # Last-resort safety net: extract_resume_json's proactive sizing
            # (safe_chunk_chars) should prevent this in the normal case, but
            # a token-estimate heuristic can be wrong for unusual text (dense
            # non-English content, code blocks). Split this one chunk in
            # half and merge — reuses the same deterministic merge already
            # used for top-level chunks, so no LLM is asked to reconcile
            # facts across the split.
            mid = len(chunk) // 2
            split_point = chunk.rfind("\n\n", 0, mid)
            if split_point <= 0:
                split_point = mid
            left, right = chunk[:split_point].strip(), chunk[split_point:].strip()
            left_resume, left_result = await _extract_valid_chunk(
                left,
                chunk_index=chunk_index,
                chunk_count=chunk_count,
                max_output_tokens=max_output_tokens,
            )
            right_resume, right_result = await _extract_valid_chunk(
                right,
                chunk_index=chunk_index,
                chunk_count=chunk_count,
                max_output_tokens=max_output_tokens,
            )
            merged = merge_resume_chunks([left_resume, right_resume])
            # Prefer the second call's provider/model for reporting — both
            # halves used the same configured provider either way.
            return merged, right_result
        raise

    if result.fallback_used:
        raise RuntimeError(
            "The configured model failed and returned development mock data; "
            "the extraction was not persisted."
        )

    try:
        resume = ResumeJSON.model_validate(_parse_json_object(result.content))
        return resume, result
    except (ValueError, ValidationError) as first_error:
        correction = await model_gateway.run_detailed(
            use_case="resume_parsing",
            system_prompt=SYSTEM_PROMPT,
            user_prompt=build_correction_prompt(result.content, str(first_error)),
            max_tokens=max_output_tokens,
        )
        if correction.fallback_used:
            raise RuntimeError("Structured-output correction fell back to mock data")
        try:
            resume = ResumeJSON.model_validate(_parse_json_object(correction.content))
        except (ValueError, ValidationError) as second_error:
            raise ValueError(
                "Model output failed strict ResumeJSON validation after one correction: "
                f"{second_error}"
            ) from second_error
        return resume, correction


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def _unique_strings(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            continue
        key = _norm(value)
        if key not in seen:
            seen.add(key)
            result.append(value.strip())
    return result


def _item_key(item: dict[str, Any], fields: tuple[str, ...]) -> tuple[str, ...]:
    key = tuple(_norm(item.get(field)) for field in fields)
    if any(key):
        return key
    return (_norm(json.dumps(item, sort_keys=True, ensure_ascii=False)),)


def _merge_dict(existing: dict[str, Any], incoming: dict[str, Any]) -> None:
    for key, value in incoming.items():
        if value in (None, "", [], {}):
            continue
        current = existing.get(key)
        if current in (None, "", [], {}):
            existing[key] = value
        elif isinstance(current, list) and isinstance(value, list):
            if all(isinstance(v, str) for v in current + value):
                existing[key] = _unique_strings(current + value)
            else:
                seen = {
                    json.dumps(v, sort_keys=True, ensure_ascii=False)
                    for v in current
                    if isinstance(v, dict)
                }
                for child in value:
                    marker = json.dumps(child, sort_keys=True, ensure_ascii=False)
                    if marker not in seen:
                        current.append(child)
                        seen.add(marker)


def _merge_items(
    target: list[dict[str, Any]], incoming: list[dict[str, Any]], key_fields: tuple[str, ...]
) -> None:
    index = {_item_key(item, key_fields): item for item in target}
    for item in incoming:
        key = _item_key(item, key_fields)
        if key in index:
            _merge_dict(index[key], item)
        else:
            copied = dict(item)
            target.append(copied)
            index[key] = copied


def merge_resume_chunks(chunks: list[ResumeJSON]) -> ResumeJSON:
    """Deterministically merge validated chunks without asking an LLM to rewrite facts."""
    merged: dict[str, Any] = ResumeJSON().model_dump(mode="json")
    contact = merged["contact"]

    list_keys: dict[str, tuple[str, ...]] = {
        "experience": ("company", "title", "start_date", "end_date"),
        "education": ("institution", "degree", "field", "end_date"),
        "projects": ("name", "role", "url"),
        "certifications": ("name", "issuer", "issue_date"),
        "awards": ("name", "issuer", "date"),
        "publications": ("name", "url", "date"),
        "volunteering": ("name", "issuer", "date"),
        "languages": ("name",),
        "additional_sections": ("title",),
        "verification_topics": ("claim", "reason"),
    }

    for chunk in chunks:
        data = chunk.model_dump(mode="json")
        _merge_dict(contact, data["contact"])
        for scalar in ("headline", "summary"):
            if not merged.get(scalar) and data.get(scalar):
                merged[scalar] = data[scalar]
        merged["skills"] = _unique_strings(merged["skills"] + data["skills"])
        merged["interests"] = _unique_strings(merged["interests"] + data["interests"])
        for group, skills in data["skill_groups"].items():
            merged["skill_groups"][group] = _unique_strings(
                merged["skill_groups"].get(group, []) + skills
            )
        for key, fields in list_keys.items():
            _merge_items(merged[key], data[key], fields)

    return ResumeJSON.model_validate(merged)


async def extract_resume_json(
    normalized_text: str,
    *,
    parse_source: str | None,
    used_ocr_fallback: bool,
) -> ExtractionResult:
    settings = get_settings()
    # Size chunks to the model actually configured right now, not just the
    # static config default — a chunk that fits Gemini's 1M-token window
    # comfortably could still be too large for a smaller local/free model.
    # Computed once per extraction (all chunks use the same model).
    fixed_prompt_chars = len(SYSTEM_PROMPT) + 300  # build_user_prompt's own wrapper text
    model_for_sizing = current_model_name("resume_parsing")
    max_output_tokens = max(
        _RESUME_EXTRACTION_MAX_TOKENS,
        max_output_tokens_for(model_for_sizing),
    )
    max_chars = min(
        settings.resume_llm_chunk_chars,
        safe_chunk_chars(
            model_name=model_for_sizing,
            fixed_prompt_chars=fixed_prompt_chars,
            max_output_tokens=max_output_tokens,
        ),
    )
    chunks = split_resume_text(
        normalized_text,
        max_chars=max_chars,
        max_chunks=settings.resume_llm_max_chunks,
    )
    if not chunks:
        raise ValueError("Resume source text is empty")

    resumes: list[ResumeJSON] = []
    raw_outputs: list[str] = []
    provider = ""
    model_name = ""
    fallback_used = False
    for index, chunk in enumerate(chunks, start=1):
        resume, result = await _extract_valid_chunk(
            chunk,
            chunk_index=index,
            chunk_count=len(chunks),
            max_output_tokens=max_output_tokens,
        )
        resumes.append(resume)
        raw_outputs.append(result.content)
        provider = result.provider
        model_name = result.model_name
        fallback_used = fallback_used or result.fallback_used

    merged = merge_resume_chunks(resumes)
    merged.extraction_metadata = ExtractionMetadata(
        parse_source=parse_source,
        model_provider=provider,
        model_name=model_name,
        prompt_version=PROMPT_VERSION,
        chunk_count=len(chunks),
        source_characters=len(normalized_text),
        used_ocr_fallback=used_ocr_fallback,
        fallback_used=fallback_used,
    )
    return ExtractionResult(
        resume=merged,
        raw_json=json.dumps(raw_outputs, ensure_ascii=False),
        provider=provider,
        model_name=model_name,
        fallback_used=fallback_used,
        chunk_count=len(chunks),
    )


def validate_resume_payload(payload: dict[str, Any]) -> ResumeJSON:
    return ResumeJSON.model_validate(payload)
