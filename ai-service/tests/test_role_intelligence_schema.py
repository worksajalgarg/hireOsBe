import pytest
from pydantic import ValidationError

from app.agents.role_intelligence_schema import (
    RequirementClaim,
    ResponsibilityClaim,
    RoleExtractionLLMOutput,
    RoleExtractionResponse,
)


def test_empty_output_is_valid_not_an_error() -> None:
    output = RoleExtractionLLMOutput()
    assert output.must_have_requirements == []
    assert output.nice_to_have_requirements == []
    assert output.responsibilities == []


def test_requirement_claim_requires_source_text() -> None:
    with pytest.raises(ValidationError):
        RequirementClaim(requirement="5+ years of Python")  # missing source_text


def test_requirement_claim_with_source_text_is_valid() -> None:
    claim = RequirementClaim(requirement="5+ years of Python", source_text="5+ years Python")
    assert claim.section is None


def test_responsibility_claim_requires_source_text() -> None:
    with pytest.raises(ValidationError):
        ResponsibilityClaim(responsibility="Own the backend architecture")


def test_unparsed_sections_accepts_partial_extraction() -> None:
    output = RoleExtractionLLMOutput(unparsed_sections=["Benefits table was garbled"])
    assert output.unparsed_sections == ["Benefits table was garbled"]


def test_response_envelope_adds_request_scoped_fields() -> None:
    response = RoleExtractionResponse(
        source_filename="jd.docx",
        extracted_text="full jd text",
        extracted_text_length=200,
        model_version="model_gateway:role_parsing",
    )
    assert response.source_filename == "jd.docx"
    assert response.must_have_requirements == []
