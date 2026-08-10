import pytest
from pydantic import ValidationError

from app.agents.resume_intelligence_schema import (
    EvidencedClaim,
    ResumeExtractionLLMOutput,
    ResumeExtractionResponse,
    SkillClaim,
    UnparsedSection,
    WorkHistoryEntry,
)


def test_empty_output_is_valid_not_an_error() -> None:
    """A thin resume with nothing extractable is a real case, not a schema
    violation — must not force fabrication to satisfy a non-empty
    constraint."""
    output = ResumeExtractionLLMOutput()
    assert output.work_history == []
    assert output.skills == []
    assert output.education == []


def test_evidenced_claim_requires_source_text() -> None:
    with pytest.raises(ValidationError):
        EvidencedClaim(claim="Led a team of 5 engineers")  # missing source_text


def test_evidenced_claim_with_source_text_is_valid() -> None:
    claim = EvidencedClaim(claim="Led a team of 5 engineers", source_text="led a team of 5")
    assert claim.section is None


def test_skill_claim_requires_source_text_not_a_generic_claim_field() -> None:
    skill = SkillClaim(skill="Python", source_text="proficient in Python")
    assert skill.skill == "Python"
    assert skill.years_experience is None
    with pytest.raises(ValidationError):
        SkillClaim(skill="Python")  # missing source_text


def test_work_history_entry_is_current_defaults_to_none_not_false() -> None:
    """None (not False) when the resume doesn't say — never a guessed
    default in either direction."""
    entry = WorkHistoryEntry(
        company="Acme", title="Engineer", source_text="Acme - Engineer"
    )
    assert entry.is_current is None
    assert entry.start_date is None
    assert entry.responsibilities == []


def test_unparsed_sections_accepts_partial_extraction() -> None:
    output = ResumeExtractionLLMOutput(
        unparsed_sections=[
            UnparsedSection(section_title="Certifications", raw_text="table was garbled")
        ]
    )
    assert output.unparsed_sections[0].section_title == "Certifications"
    assert output.unparsed_sections[0].raw_text == "table was garbled"


def test_response_envelope_adds_request_scoped_fields() -> None:
    response = ResumeExtractionResponse(
        source_filename="resume.pdf",
        extracted_text_length=120,
        model_version="model_gateway:resume_parsing",
    )
    assert response.source_filename == "resume.pdf"
    assert response.work_history == []
