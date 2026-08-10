"""Structured resume-extraction shape — the Resume Evidence Agent's hard
boundary (see resume_intelligence.py's module docstring) is "cannot infer
missing experience as fact." EvidencedClaim is the concrete mechanism for
that: no claim field exists without a mandatory source_text pointer back
into the resume text the model was given. Content the model can't
confidently structure goes into unparsed_sections instead of being guessed
at — same "never invent, assume, or infer" rigor as
voice_agent/post_call_evaluation.py's evaluation prompt, applied here to
extraction instead of judgment.

Plain nested pydantic.BaseModel classes, snake_case, no platform DTO to
match yet (unlike evaluation_schema.py) — this endpoint has no downstream
consumer in platform today, so there's no reason to add to_camel aliasing
ahead of an actual integration.
"""

from pydantic import BaseModel, field_validator, model_validator


def _drop_missing(items: object, key: str) -> object:
    """Enforces "omit an entry you can't ground" at the code level instead
    of only asking for it in the prompt: a small model on a long, many-field
    schema occasionally violates that rule directly (emits an entry with
    source_text/raw_text: null, or the whole list as null) rather than
    leaving the entry/list out — confirmed in practice against real Groq
    output on real resumes. Silently dropping the offending item (or
    treating a null list as empty) means one such slip degrades that one
    entry instead of invalidating the entire structured response and
    forcing a retry/fallback. Never fabricates a source_text — only removes
    entries that have none."""
    if items is None:
        return []
    if not isinstance(items, list):
        return items

    def _has_key(item: object) -> bool:
        if isinstance(item, dict):
            return bool(item.get(key))
        return bool(getattr(item, key, None))

    return [item for item in items if _has_key(item)]


def _none_to_empty_list(items: object) -> object:
    return [] if items is None else items


class SourceGrounded(BaseModel):
    """Shared evidence-grounding fields — never a bare LLM assertion with no
    pointer back to source text. A claim the model can't ground in the
    actual resume text must be omitted from its list entirely, never
    included with an empty/fabricated source_text. Domain-specific
    subclasses add their own primary field (skill, requirement, ...) rather
    than inheriting a generic `claim` field, so the model isn't asked to
    fill in two redundant copies of the same fact."""

    source_text: str
    section: str | None = None


class EvidencedClaim(SourceGrounded):
    """Generic evidence-grounded claim, for lists where the claim itself
    doesn't need a more specific field name (education entries, a job's
    responsibility bullets)."""

    claim: str


class WorkHistoryEntry(BaseModel):
    company: str
    title: str
    start_date: str | None = None
    end_date: str | None = None
    is_current: bool | None = None
    responsibilities: list[EvidencedClaim] = []
    source_text: str

    @field_validator("responsibilities", mode="before")
    @classmethod
    def _drop_ungrounded_responsibilities(cls, v: object) -> object:
        return _drop_missing(v, "source_text")

    @model_validator(mode="before")
    @classmethod
    def _fill_missing_source_text(cls, data: object) -> object:
        """source_text here is a short identifying line, not the primary
        evidence mechanism (each responsibility carries its own) — so
        rather than dropping an otherwise-good entry over a missing/null
        source_text, derive it from the entry's own already-verbatim
        company/title fields. Never invents new information, just reuses
        what the model already reported for this same entry."""
        if isinstance(data, dict) and not data.get("source_text"):
            company = (data.get("company") or "").strip()
            title = (data.get("title") or "").strip()
            fallback = " — ".join(p for p in (company, title) if p) or "unspecified"
            data = {**data, "source_text": fallback}
        return data


class SkillClaim(SourceGrounded):
    skill: str
    years_experience: int | None = None


class UnparsedSection(BaseModel):
    """A genuinely unmodeled resume section (e.g. "Hobbies", "References
    available on request") — captures the section's actual content instead
    of a lossy one-line description, so nothing a resume contains is
    silently discarded just because it doesn't fit a known bucket."""

    section_title: str
    raw_text: str
    # Additive, default True so the LLM's own output (which never sets
    # this) and every existing call site keep working unmodified — the
    # real value is computed and overwritten in resume_intelligence.py's
    # route handler via _has_substantial_content, after backfill/dedup
    # have run, so it reflects the final raw_text. Distinguishes "real,
    # substantial content that just doesn't fit a known field" (True, no
    # UI alarm warranted) from "genuinely thin/ambiguous" (False, the
    # frontend's "Could not confidently parse" warning is earned).
    has_content: bool = True


class ResumeExtractionLLMOutput(BaseModel):
    """What the LLM produces via model_gateway.run_structured — see
    resume_intelligence.py for how this becomes the API response.

    Every list field beyond the original core five (work_history, skills,
    education, contact, candidate_name) follows the same EvidencedClaim
    evidence-grounding pattern deliberately — no new claim shapes, so
    EvidenceList (frontend) renders all of them for free."""

    candidate_name: str | None = None
    # The candidate's location as stated on the resume (city/region/country,
    # however granular the resume states it) — separate from contact since
    # it's not a reachable channel. None if the resume doesn't state one.
    location: str | None = None
    # str | None, not str — real LLM output includes e.g. {"email": "...",
    # "phone": null} when only one contact field is present on the resume,
    # rather than omitting the key entirely. Tolerate that instead of
    # rejecting an otherwise-valid extraction over it. May also carry
    # "linkedin"/"github"/"portfolio" keys when the resume has them.
    contact: dict[str, str | None] = {}
    # The resume's own summary/objective paragraph, verbatim or
    # near-verbatim — never synthesized from scattered facts elsewhere on
    # the resume. None if the resume has no such section.
    professional_summary: str | None = None
    work_history: list[WorkHistoryEntry] = []
    skills: list[SkillClaim] = []
    education: list[EvidencedClaim] = []
    certifications: list[EvidencedClaim] = []
    projects: list[EvidencedClaim] = []
    awards: list[EvidencedClaim] = []
    publications: list[EvidencedClaim] = []
    languages: list[EvidencedClaim] = []
    verification_topics: list[str] = []
    unparsed_sections: list[UnparsedSection] = []

    @field_validator("work_history", mode="before")
    @classmethod
    def _work_history_none_to_empty(cls, v: object) -> object:
        return _none_to_empty_list(v)

    @field_validator(
        "skills", "education", "certifications", "projects", "awards",
        "publications", "languages", mode="before",
    )
    @classmethod
    def _drop_ungrounded_claims(cls, v: object) -> object:
        return _drop_missing(v, "source_text")

    @field_validator("unparsed_sections", mode="before")
    @classmethod
    def _drop_incomplete_unparsed_sections(cls, v: object) -> object:
        return _drop_missing(v, "raw_text")

    @field_validator("verification_topics", mode="before")
    @classmethod
    def _keep_only_string_topics(cls, v: object) -> object:
        """The model occasionally returns a topic as an object (e.g.
        {"question": "...", "reason": "..."}) instead of a plain string —
        drop those rather than failing the whole response over a field
        that's advisory, not evidence-critical."""
        if v is None:
            return []
        if not isinstance(v, list):
            return v
        return [item for item in v if isinstance(item, str)]


class ResumeExtractionResponse(ResumeExtractionLLMOutput):
    """Full API response envelope — adds fields the LLM has no reliable way
    to self-report, filled in programmatically by the route handler (same
    split as evaluation_schema.py's EvaluationLLMOutput -> InterviewEvaluationSummary)."""

    source_filename: str
    extracted_text_length: int
    model_version: str
