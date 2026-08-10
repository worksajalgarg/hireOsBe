"""
Role Context Agent boundary (PRD Section 7.1). Hard boundary: cannot publish
a rubric without user approval — that approval gate belongs to a future
role-context/apps-platform feature, not here. This endpoint only extracts
what's stated in a job description; it never produces or publishes a rubric.

Internal-only endpoint for now: no auth/tenant-scoping, no upload/storage
wiring — see resume_intelligence.py's module docstring for the same caveat,
which applies identically here.
"""

import asyncio
import logging

from fastapi import APIRouter, File, HTTPException, UploadFile

from ..model_gateway.gateway import model_gateway
from .parsing import ParsedDocument, ParsingError, UnsupportedFileTypeError, parse_document
from .role_intelligence_schema import RoleExtractionLLMOutput, RoleExtractionResponse

logger = logging.getLogger("role_intelligence")

router = APIRouter(prefix="/role-intelligence", tags=["role-intelligence"])

USE_CASE = "role_parsing"

_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10MB
_MIN_EXTRACTABLE_CHARS = 50  # below this, likely a scanned/image-only file
_PARSE_TIMEOUT_S = 15.0
# Below this, a genuinely short JD (a one-line posting) legitimately having
# nothing to extract is plausible — above it, a fully empty result is far
# more likely a weak/failed extraction than a JD with truly nothing in it.
_MIN_CHARS_FOR_EMPTY_CHECK = 300

_ROLE_SYSTEM_PROMPT = """You are extracting structured data from a job description for a \
recruiter to review. Extract strictly based on what is actually written in the text provided \
— never invent, assume, or infer a requirement or responsibility not directly evidenced by the \
text.

Respond with ONLY a single JSON object — no prose, no markdown code fences, no commentary \
before or after. Required shape (use exactly these field names, nothing else — snake_case, \
matching the schema field names exactly, not camelCase):

{
  "role_title": "string or null",
  "must_have_requirements": [
    {"requirement": "string", "source_text": "verbatim quote", "section": "string or null"}
  ],
  "nice_to_have_requirements": [
    {"requirement": "string", "source_text": "verbatim quote", "section": "string or null"}
  ],
  "responsibilities": [
    {"responsibility": "string", "source_text": "verbatim quote", "section": "string or null"}
  ],
  "unparsed_sections": ["string", ...]
}

Rules:
- Every requirement's primary field is "requirement" (never "text" or "description"); every \
responsibility's primary field is "responsibility" (never "text" or "description"). Every \
entry's "source_text" is a separate field alongside its primary field — never nest the primary \
field's text inside a "text" sub-object.
- Every requirement/responsibility must include the verbatim or near-verbatim source_text it \
was extracted from. If you cannot point to specific text supporting it, omit it entirely rather \
than including it without solid grounding.
- Distinguish must_have_requirements from nice_to_have_requirements only when the text itself \
signals the distinction (e.g. "required" vs. "preferred/bonus") — if the text doesn't \
distinguish, place the requirement in must_have_requirements rather than guessing.
- unparsed_sections is a list of plain strings (a short description of the ambiguous section), \
never a list of objects — if a section is ambiguous, garbled by extraction, or you cannot \
confidently structure it, add a short string describing it instead of guessing at its content.
- Do not produce a rubric, scoring criteria, or a hiring recommendation of any kind — this \
extraction only structures what the job description already says."""


def _is_suspiciously_empty(output: RoleExtractionLLMOutput, char_count: int) -> bool:
    """A schema-valid but fully empty extraction on a substantial JD is a
    weak-model failure, not a real "this JD has no requirements" result —
    model_gateway.run_structured() only validates JSON shape, not whether
    anything meaningful was actually extracted, so this check catches what
    the schema validator structurally cannot. Confirmed necessary in
    practice: a free-tier model returned exactly this shape (all lists
    empty, no unparsed_sections either) for a real ~500-word JD."""
    if char_count < _MIN_CHARS_FOR_EMPTY_CHECK:
        return False
    return not (
        output.must_have_requirements
        or output.nice_to_have_requirements
        or output.responsibilities
        or output.unparsed_sections
    )


@router.get("/health")
async def health() -> dict[str, str]:
    return {"agent": "role-intelligence", "status": "ok"}


@router.post("/parse", response_model=RoleExtractionResponse)
async def parse_role(file: UploadFile = File(...)) -> RoleExtractionResponse:
    data = await file.read()
    if len(data) > _MAX_FILE_BYTES:
        raise HTTPException(413, f"file exceeds {_MAX_FILE_BYTES // (1024 * 1024)}MB limit")

    filename = file.filename or ""
    try:
        parsed: ParsedDocument = await asyncio.wait_for(
            asyncio.to_thread(parse_document, data, filename, file.content_type),
            timeout=_PARSE_TIMEOUT_S,
        )
    except UnsupportedFileTypeError as exc:
        raise HTTPException(415, str(exc)) from exc
    except ParsingError as exc:
        raise HTTPException(422, f"could not parse document: {exc}") from exc
    except (TimeoutError, asyncio.TimeoutError) as exc:
        logger.warning("role parse timed out after %.0fs: %s", _PARSE_TIMEOUT_S, filename)
        raise HTTPException(422, "document took too long to parse") from exc

    if parsed.char_count < _MIN_EXTRACTABLE_CHARS:
        raise HTTPException(
            422, "document has no extractable text (possibly a scanned image)"
        )

    try:
        llm_output = await model_gateway.run_structured(
            use_case=USE_CASE,
            system_prompt=_ROLE_SYSTEM_PROMPT,
            user_prompt=parsed.text,
            schema=RoleExtractionLLMOutput,
        )
    except Exception as exc:
        logger.exception("role_parsing failed for %s", filename)
        raise HTTPException(502, "extraction failed, try again") from exc

    if _is_suspiciously_empty(llm_output, parsed.char_count):
        logger.warning(
            "role_parsing returned an empty extraction for a %d-char JD (%s) — "
            "treating as a failure rather than persisting it",
            parsed.char_count, filename,
        )
        raise HTTPException(502, "extraction produced no results, try again")

    return RoleExtractionResponse(
        **llm_output.model_dump(),
        source_filename=parsed.source_filename,
        extracted_text=parsed.text,
        extracted_text_length=parsed.char_count,
        model_version=f"model_gateway:{USE_CASE}",
    )
