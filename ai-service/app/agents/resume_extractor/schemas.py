"""Strict contracts for structured resumes and extraction progress events."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """Reject model-created fields that are not part of the approved contract."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class StageName(str, Enum):
    UPLOAD_RECEIVED = "upload_received"
    FILE_VALIDATION = "file_validation"
    DOCLING = "docling"
    OCR_FALLBACK = "ocr_fallback"
    TEXT_NORMALIZATION = "text_normalization"
    LLM_EXTRACTION = "llm_extraction"
    PYDANTIC_VALIDATION = "pydantic_validation"
    FINAL_JSON = "final_json"
    ERROR = "error"


class StageStatus(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class StageEvent(StrictModel):
    stage: StageName
    status: StageStatus
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class EvidenceRef(StrictModel):
    """Short verbatim source anchor; never an LLM interpretation."""

    quote: str = Field(min_length=1, max_length=500)
    section: str | None = Field(default=None, max_length=120)
    page: int | None = Field(default=None, ge=1)


class ContactInfo(StrictModel):
    full_name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=80)
    location: str | None = Field(default=None, max_length=240)
    linkedin: str | None = Field(default=None, max_length=500)
    website: str | None = Field(default=None, max_length=500)
    github: str | None = Field(default=None, max_length=500)
    other_links: list[str] = Field(default_factory=list, max_length=20)


class ExperienceItem(StrictModel):
    company: str | None = Field(default=None, max_length=240)
    title: str | None = Field(default=None, max_length=240)
    employment_type: str | None = Field(default=None, max_length=100)
    start_date: str | None = Field(default=None, max_length=40)
    end_date: str | None = Field(default=None, max_length=40)
    is_current: bool | None = None
    location: str | None = Field(default=None, max_length=240)
    description: str | None = Field(default=None, max_length=2000)
    highlights: list[str] = Field(default_factory=list, max_length=30)
    technologies: list[str] = Field(default_factory=list, max_length=60)
    evidence: list[EvidenceRef] = Field(default_factory=list, max_length=10)


class EducationItem(StrictModel):
    institution: str | None = Field(default=None, max_length=300)
    degree: str | None = Field(default=None, max_length=240)
    field: str | None = Field(default=None, max_length=240)
    start_date: str | None = Field(default=None, max_length=40)
    end_date: str | None = Field(default=None, max_length=40)
    grade: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=240)
    highlights: list[str] = Field(default_factory=list, max_length=20)
    evidence: list[EvidenceRef] = Field(default_factory=list, max_length=10)


class ProjectItem(StrictModel):
    name: str | None = Field(default=None, max_length=240)
    role: str | None = Field(default=None, max_length=240)
    start_date: str | None = Field(default=None, max_length=40)
    end_date: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=2000)
    highlights: list[str] = Field(default_factory=list, max_length=30)
    technologies: list[str] = Field(default_factory=list, max_length=60)
    url: str | None = Field(default=None, max_length=500)
    evidence: list[EvidenceRef] = Field(default_factory=list, max_length=10)


class CertificationItem(StrictModel):
    name: str | None = Field(default=None, max_length=300)
    issuer: str | None = Field(default=None, max_length=240)
    issue_date: str | None = Field(default=None, max_length=40)
    expiry_date: str | None = Field(default=None, max_length=40)
    credential_id: str | None = Field(default=None, max_length=200)
    credential_url: str | None = Field(default=None, max_length=500)
    evidence: list[EvidenceRef] = Field(default_factory=list, max_length=10)


class LanguageItem(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    proficiency: str | None = Field(default=None, max_length=100)


class NamedDetailItem(StrictModel):
    name: str = Field(min_length=1, max_length=300)
    detail: str | None = Field(default=None, max_length=2000)
    date: str | None = Field(default=None, max_length=40)
    issuer: str | None = Field(default=None, max_length=240)
    url: str | None = Field(default=None, max_length=500)
    evidence: list[EvidenceRef] = Field(default_factory=list, max_length=10)


class AdditionalSection(StrictModel):
    title: str = Field(min_length=1, max_length=160)
    items: list[str] = Field(default_factory=list, max_length=100)


class VerificationTopic(StrictModel):
    claim: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=500)
    evidence: list[EvidenceRef] = Field(default_factory=list, max_length=5)


class ExtractionMetadata(StrictModel):
    parse_source: str | None = None
    model_provider: str | None = None
    model_name: str | None = None
    prompt_version: str = "resume-extraction-v2"
    chunk_count: int = Field(default=1, ge=1)
    source_characters: int = Field(default=0, ge=0)
    used_ocr_fallback: bool = False
    fallback_used: bool = False


class ResumeJSON(StrictModel):
    """Complete, grounded resume representation after deterministic merging."""

    schema_version: Literal["2.0"] = "2.0"
    contact: ContactInfo = Field(default_factory=ContactInfo)
    headline: str | None = Field(default=None, max_length=300)
    summary: str | None = Field(default=None, max_length=3000)
    experience: list[ExperienceItem] = Field(default_factory=list, max_length=100)
    education: list[EducationItem] = Field(default_factory=list, max_length=50)
    skills: list[str] = Field(default_factory=list, max_length=300)
    skill_groups: dict[str, list[str]] = Field(default_factory=dict)
    projects: list[ProjectItem] = Field(default_factory=list, max_length=100)
    certifications: list[CertificationItem] = Field(default_factory=list, max_length=100)
    awards: list[NamedDetailItem] = Field(default_factory=list, max_length=100)
    publications: list[NamedDetailItem] = Field(default_factory=list, max_length=100)
    volunteering: list[NamedDetailItem] = Field(default_factory=list, max_length=100)
    languages: list[LanguageItem] = Field(default_factory=list, max_length=100)
    interests: list[str] = Field(default_factory=list, max_length=100)
    additional_sections: list[AdditionalSection] = Field(default_factory=list, max_length=50)
    verification_topics: list[VerificationTopic] = Field(default_factory=list, max_length=50)
    extraction_metadata: ExtractionMetadata = Field(default_factory=ExtractionMetadata)
