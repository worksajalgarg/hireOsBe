"""Structured job-description-extraction shape — mirrors
resume_intelligence_schema.py's evidence-traceability pattern (see that
file's module docstring). The Role Context Agent's hard boundary here is
narrower than resume parsing's: this only extracts what's stated in the JD
text, it never publishes a rubric (see role_intelligence.py's module
docstring) — that approval-gated step belongs to a future role-context
feature, not this one.
"""

from pydantic import BaseModel

from .resume_intelligence_schema import SourceGrounded


class RequirementClaim(SourceGrounded):
    requirement: str


class ResponsibilityClaim(SourceGrounded):
    responsibility: str


class RoleExtractionLLMOutput(BaseModel):
    """What the LLM produces via model_gateway.run_structured — see
    role_intelligence.py for how this becomes the API response."""

    role_title: str | None = None
    must_have_requirements: list[RequirementClaim] = []
    nice_to_have_requirements: list[RequirementClaim] = []
    responsibilities: list[ResponsibilityClaim] = []
    unparsed_sections: list[str] = []


class RoleExtractionResponse(RoleExtractionLLMOutput):
    """Full API response envelope — same split as
    ResumeExtractionResponse/InterviewEvaluationSummary.

    extracted_text is the plain text pulled from the JD file (or the pasted
    text platform sent) — included here (unlike ResumeExtractionResponse)
    so platform can persist JobRole.jdText without re-parsing the file
    client-side. Resumes deliberately don't get this: platform has no need
    to store a resume's raw body separately from the file itself."""

    source_filename: str
    extracted_text: str
    extracted_text_length: int
    model_version: str
