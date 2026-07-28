"""Pydantic models for resume JSON and SSE stage events."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


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


class StageEvent(BaseModel):
    stage: StageName
    status: StageStatus
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class ContactInfo(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    linkedin: str | None = None
    website: str | None = None


class ExperienceItem(BaseModel):
    company: str | None = None
    title: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    location: str | None = None
    highlights: list[str] = Field(default_factory=list)


class EducationItem(BaseModel):
    institution: str | None = None
    degree: str | None = None
    field: str | None = None
    start_date: str | None = None
    end_date: str | None = None


class ResumeJSON(BaseModel):
    """Validated structured resume output after LLM extraction."""

    contact: ContactInfo = Field(default_factory=ContactInfo)
    summary: str | None = None
    experience: list[ExperienceItem] = Field(default_factory=list)
    education: list[EducationItem] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
