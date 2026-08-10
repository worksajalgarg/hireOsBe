"""
Resume Evidence Agent boundary (PRD Section 7.1). Hard boundary: cannot
infer missing experience as fact — enforced by resume_intelligence_schema's
SourceGrounded fields (every claim carries a mandatory source_text quote)
and by _RESUME_SYSTEM_PROMPT's explicit "never invent or infer" rule.

Internal-only endpoint for now: no auth/tenant-scoping, no upload/storage
wiring (no upload flow exists anywhere in either repo yet — see
hireOsBe's migration plan). Accepts file bytes directly; a future
platform-mediated upload flow is separate work.
"""

import asyncio
import logging
import re

from fastapi import APIRouter, File, HTTPException, UploadFile

from ..model_gateway.gateway import model_gateway
from .document_intake_limits import (
    MAX_FILE_BYTES,
    MIN_CHARS_FOR_EMPTY_CHECK,
    MIN_EXTRACTABLE_CHARS,
    PARSE_TIMEOUT_S,
)
from .parsing import ParsedDocument, ParsingError, UnsupportedFileTypeError, parse_document
from .resume_intelligence_schema import (
    ResumeExtractionLLMOutput,
    ResumeExtractionResponse,
    UnparsedSection,
)

logger = logging.getLogger("resume_intelligence")

router = APIRouter(prefix="/resume-intelligence", tags=["resume-intelligence"])

USE_CASE = "resume_parsing"

_RESUME_SYSTEM_PROMPT = """You are extracting structured data from a candidate's resume for a \
recruiter to review. Extract strictly based on what is actually written in the resume text \
provided — never invent, assume, or infer a claim not directly evidenced by the text.

Respond with ONLY a single JSON object — no prose, no markdown code fences, no commentary \
before or after. Required shape (use exactly these field names, nothing else — snake_case, \
matching the schema field names exactly, not camelCase):

{
  "candidate_name": "string or null",
  "location": "city/region/country as stated on the resume header, or null if not stated",
  "contact": {"email": "...", "phone": "...", "linkedin": "... or omit", "github": "... or omit",
              "portfolio": "... or omit"},
  "professional_summary": "verbatim/near-verbatim summary paragraph, or null if none exists",
  "work_history": [
    {
      "company": "string", "title": "string",
      "start_date": "free text as written, or null",
      "end_date": "free text as written, or null",
      "is_current": true, false, or null (null unless the resume explicitly says current),
      "responsibilities": [
        {"claim": "string", "source_text": "verbatim quote", "section": "string or null"}
      ],
      "source_text": "REQUIRED — a short line, e.g. 'Acme Inc — Engineer — Jan 2020 - Present', \
never omitted and never the full block of bullets"
    }
  ],
  "skills": [
    {"skill": "string", "source_text": "verbatim quote", "section": "string or null",
     "years_experience": integer or null}
  ],
  "education": [{"claim": "string", "source_text": "verbatim quote", "section": "str or null"}],
  "certifications": [{"claim": "str", "source_text": "verbatim quote", "section": "str or null"}],
  "projects": [{"claim": "string", "source_text": "verbatim quote", "section": "str or null"}],
  "awards": [{"claim": "string", "source_text": "verbatim quote", "section": "str or null"}],
  "publications": [{"claim": "string", "source_text": "verbatim quote", "section": "str or null"}],
  "languages": [{"claim": "string", "source_text": "verbatim quote", "section": "str or null"}],
  "verification_topics": ["string", ...],
  "unparsed_sections": [{"section_title": "string", "raw_text": "the section's actual text"}]
}

Rules:
- Every claim (a skill, a responsibility, an education/certification/project/award/publication/\
language entry) must include the verbatim or near-verbatim source_text it was extracted from. \
source_text is NEVER null and NEVER omitted from an entry you do include — if you cannot point to \
specific text supporting a claim, the fix is to leave the whole entry out of the list entirely, \
never to include it with a null or missing source_text.
- Only include a field's list/value at all if the resume actually has that kind of content — \
e.g. return an empty list [] for certifications/projects/awards/publications/languages when the \
resume has none, and null for professional_summary when there's no summary/objective section. \
Never include a placeholder entry with null/empty fields just to show a field was considered.
- professional_summary is verbatim or near-verbatim text actually written in a \
summary/objective/profile section — never synthesized or inferred from other parts of the resume.
- A skill's primary field is "skill" (the skill name itself, e.g. "Python") — never "name" or \
"language" or any other field name. certifications/projects/awards/publications/languages entries \
each use "claim" as their primary field (e.g. a project's claim is its name plus a short \
description; a language entry's claim is the language, and proficiency if stated).
- If skills are listed as a comma-separated group under a category label (e.g. "Front-end: \
Next.js, React.js, HTML, CSS"), emit one skill entry per individual skill named — "Next.js", \
"React.js", "HTML", "CSS" as four separate entries, each with its own source_text, each using \
"skill" as the primary field name (never "claim" — that reminder applies to every one of these \
entries, not just the first few). Never emit the category label itself ("Front-end", "Tools & \
Platforms", ...) as a skill entry, and never skip an individual skill just because it appeared \
inside a category list — every named skill across every category must get its own entry.
- work_history[].source_text is only the entry's identifying line (company, title, dates) — do \
not repeat the full block of bullets there, since each bullet already has its own source_text in \
responsibilities. Keep this field short.
- If a section of the resume is ambiguous, garbled by extraction, or genuinely doesn't fit any \
field above, add it to unparsed_sections as {"section_title": ..., "raw_text": ...} — raw_text is \
the section's actual text content, not a one-line description of it. Never drop content silently.
- Dates (start_date/end_date) are free text exactly as written in the resume — do not compute, \
normalize, or infer a missing end date as "present"; leave is_current null unless the \
resume explicitly says the role is current.
- verification_topics is a list of plain strings, never objects (no {"question": ...} or similar \
— just the string itself). Each should name a specific thing worth probing in an interview: thin \
or vague claims, unexplained gaps, or claims that would benefit from verification — not a \
restatement of the resume's contents."""


# How far past section_title's own length raw_text must reach before it's
# treated as real body text rather than a lazy echo of the label.
_THIN_RAW_TEXT_MARGIN = 10
# Bounded window of source text to pull following a section heading — wide
# enough for a real paragraph/bullet block, capped so a failed cut-point
# search can't drag in unrelated later sections.
_BACKFILL_WINDOW_CHARS = 800


def _backfill_thin_unparsed_sections(
    sections: list[UnparsedSection], source_text: str
) -> list[UnparsedSection]:
    """The model sometimes flags a section it can't classify but echoes the
    heading back as raw_text instead of the actual body text beneath it
    (confirmed in practice: a real resume's "Courses" section came back as
    {"section_title": "Courses", "raw_text": "Courses"}, and the real
    content — two bullets — was lost nowhere else in the response either).
    Recovering it from the source text is a verbatim-quote guarantee that
    doesn't depend on the model complying with the prompt's instruction —
    the same principle already backing every other field in this schema.

    Deliberately title-blind to what's already been extracted elsewhere —
    see resume_intelligence's fix plan for why that's an accepted tradeoff,
    not a bug: a section whose real content is already captured under e.g.
    work_history will get backfilled too (duplicating it here), which is a
    cosmetic downside, not a data-loss or fabrication risk.

    Confirmed in practice this can go wrong in a different way: when two
    orphaned heading-only labels end up adjacent in the source text (a real
    docling PDF-layout artifact — a resume's small italic "Courses" and
    "Achievements" captions both got extracted as standalone lines at the
    very end of the document, nowhere near the bullets they actually
    caption), a naive "grab the text right after the heading" recovers the
    *next heading* rather than real content. Guards against that by
    rejecting a recovered body that's itself just another section's title
    (or still too thin) — in that case the source text genuinely has no
    real content adjacent to this heading (a document-parsing-layer
    limitation this function can't fix), so the section is left as the
    model produced it rather than substituting actively misleading text."""
    known_titles = {s.section_title.strip().lower() for s in sections}
    backfilled: list[UnparsedSection] = []
    for section in sections:
        title = section.section_title.strip()
        raw = section.raw_text.strip()
        if len(raw) > len(title) + _THIN_RAW_TEXT_MARGIN:
            backfilled.append(section)
            continue

        match = re.search(re.escape(title), source_text, re.IGNORECASE)
        if match is None:
            backfilled.append(section)  # can't locate it — leave as-is, don't guess
            continue

        window = source_text[match.end() : match.end() + _BACKFILL_WINDOW_CHARS]
        # Cut at the next paragraph break so we don't overreach into an
        # unrelated later section; only trust it if it leaves a real block.
        break_idx = window.find("\n\n")
        body = (window[:break_idx] if break_idx > 20 else window).strip()

        looks_like_another_heading = not body or body.lower() in known_titles
        still_too_thin = len(body) <= len(title) + _THIN_RAW_TEXT_MARGIN
        if looks_like_another_heading or still_too_thin:
            backfilled.append(section)  # would just substitute one label for another
            continue

        backfilled.append(UnparsedSection(section_title=section.section_title, raw_text=body))
    return backfilled


def _drop_unparsed_sections_captured_elsewhere(
    sections: list[UnparsedSection], output: ResumeExtractionLLMOutput
) -> list[UnparsedSection]:
    """_backfill_thin_unparsed_sections above is deliberately title-blind
    (see its own docstring) — it can end up recovering real content for a
    section whose content the model *also* already captured under e.g.
    education, producing a duplicate stub (confirmed in practice on a real
    resume: "Courses"/"Achievements" showed up both here and, correctly,
    under education). That duplication was an accepted cosmetic tradeoff
    when backfill was written, but it's avoidable now without touching
    backfill itself or the prompt (a prompt-level fix for this exact kind
    of thing already backfired once this session — see this function's
    sibling comment history — so this stays code-level and deterministic).

    Only drops a section when its title exact-matches (case-insensitive) a
    `section` value the model already reported on a real, grounded claim
    elsewhere — never a fuzzy text-similarity check, so it can't misfire on
    a genuinely-unparsed section that merely shares wording with a real
    one."""
    captured_titles = {
        entry.section.strip().lower()
        for field in (
            output.education,
            output.certifications,
            output.projects,
            output.awards,
            output.publications,
            output.languages,
        )
        for entry in field
        if entry.section
    }
    return [s for s in sections if s.section_title.strip().lower() not in captured_titles]


def _is_suspiciously_empty(output: ResumeExtractionLLMOutput, char_count: int) -> bool:
    if char_count < MIN_CHARS_FOR_EMPTY_CHECK:
        return False
    return not (
        output.work_history
        or output.skills
        or output.education
        or output.certifications
        or output.projects
        or output.awards
        or output.publications
        or output.languages
        or output.professional_summary
        or output.unparsed_sections
    )


@router.get("/health")
async def health() -> dict[str, str]:
    return {"agent": "resume-intelligence", "status": "ok"}


@router.post("/parse", response_model=ResumeExtractionResponse)
async def parse_resume(file: UploadFile = File(...)) -> ResumeExtractionResponse:
    data = await file.read()
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(413, f"file exceeds {MAX_FILE_BYTES // (1024 * 1024)}MB limit")

    filename = file.filename or ""
    try:
        parsed: ParsedDocument = await asyncio.wait_for(
            asyncio.to_thread(parse_document, data, filename, file.content_type),
            timeout=PARSE_TIMEOUT_S,
        )
    except UnsupportedFileTypeError as exc:
        raise HTTPException(415, str(exc)) from exc
    except ParsingError as exc:
        raise HTTPException(422, f"could not parse document: {exc}") from exc
    except (TimeoutError, asyncio.TimeoutError) as exc:
        # Python <3.11's asyncio.TimeoutError isn't the same class as the
        # builtin TimeoutError (they unified in 3.11) — catch both so this
        # works identically on the 3.12 deploy target and older local envs.
        logger.warning("resume parse timed out after %.0fs: %s", PARSE_TIMEOUT_S, filename)
        raise HTTPException(422, "document took too long to parse") from exc

    if parsed.char_count < MIN_EXTRACTABLE_CHARS:
        raise HTTPException(
            422, "document has no extractable text (possibly a scanned image)"
        )

    try:
        llm_output = await model_gateway.run_structured(
            use_case=USE_CASE,
            system_prompt=_RESUME_SYSTEM_PROMPT,
            user_prompt=parsed.text,
            schema=ResumeExtractionLLMOutput,
        )
    except Exception as exc:
        logger.exception("resume_parsing failed for %s", filename)
        raise HTTPException(502, "extraction failed, try again") from exc

    llm_output.unparsed_sections = _backfill_thin_unparsed_sections(
        llm_output.unparsed_sections, parsed.text
    )
    llm_output.unparsed_sections = _drop_unparsed_sections_captured_elsewhere(
        llm_output.unparsed_sections, llm_output
    )

    if _is_suspiciously_empty(llm_output, parsed.char_count):
        logger.warning(
            "resume_parsing returned an empty extraction for a %d-char resume (%s) — "
            "treating as a failure rather than persisting it",
            parsed.char_count, filename,
        )
        raise HTTPException(502, "extraction produced no results, try again")

    return ResumeExtractionResponse(
        **llm_output.model_dump(),
        source_filename=parsed.source_filename,
        extracted_text_length=parsed.char_count,
        model_version=f"model_gateway:{USE_CASE}",
    )
