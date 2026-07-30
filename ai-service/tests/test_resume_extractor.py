"""Unit tests for resume extractor validation, normalize, and schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agents.resume_extractor.normalize import normalize_text
from app.agents.resume_extractor.schemas import ResumeJSON
from app.agents.resume_extractor.validation import FileValidationError, validate_upload


def test_validate_upload_rejects_unsupported_extension() -> None:
    with pytest.raises(FileValidationError, match="Unsupported file type"):
        validate_upload(
            filename="resume.exe",
            content_type="application/octet-stream",
            size_bytes=100,
        )


def test_validate_upload_accepts_doc_and_docx() -> None:
    from app.config import get_settings

    get_settings.cache_clear()
    for name, ctype in (
        ("resume.doc", "application/msword"),
        ("resume.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("scan.png", "image/png"),
        ("notes.md", "text/markdown"),
    ):
        result = validate_upload(filename=name, content_type=ctype, size_bytes=2048)
        assert result.filename == name


def test_validate_upload_rejects_empty_file() -> None:
    with pytest.raises(FileValidationError, match="empty"):
        validate_upload(
            filename="resume.pdf",
            content_type="application/pdf",
            size_bytes=0,
        )


def test_validate_upload_rejects_oversized(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("RESUME_MAX_UPLOAD_MB", "1")
    get_settings.cache_clear()

    with pytest.raises(FileValidationError, match="exceeds maximum"):
        validate_upload(
            filename="big.pdf",
            content_type="application/pdf",
            size_bytes=2 * 1024 * 1024,
        )

    get_settings.cache_clear()


def test_validate_upload_accepts_pdf() -> None:
    from app.config import get_settings

    get_settings.cache_clear()
    result = validate_upload(
        filename="Jane_Doe.pdf",
        content_type="application/pdf",
        size_bytes=12_345,
    )
    assert result.extension == ".pdf"
    assert result.filename == "Jane_Doe.pdf"


def test_normalize_collapses_whitespace() -> None:
    raw = "Hello,\t\tworld.\r\n\r\n\r\n  Next   line  "
    assert normalize_text(raw) == "Hello, world.\n\nNext line"


def test_normalize_truncates() -> None:
    raw = "a" * 100
    out = normalize_text(raw, max_chars=50)
    assert out.endswith("[truncated]")
    assert len(out) < 100


def test_resume_json_accepts_fixture() -> None:
    payload = {
        "contact": {
            "full_name": "Ada Lovelace",
            "email": "ada@example.com",
            "phone": None,
            "location": "London",
            "linkedin": None,
            "website": None,
        },
        "summary": "Mathematician and writer.",
        "experience": [
            {
                "company": "Analytical Engine",
                "title": "Collaborator",
                "start_date": "1842",
                "end_date": "1843",
                "location": None,
                "highlights": ["Wrote early algorithm notes"],
            }
        ],
        "education": [
            {
                "institution": "Private tutors",
                "degree": None,
                "field": "Mathematics",
                "start_date": None,
                "end_date": None,
            }
        ],
        "skills": ["Mathematics", "Writing"],
        "certifications": [],
        "languages": ["English"],
    }
    resume = ResumeJSON.model_validate(payload)
    assert resume.contact.full_name == "Ada Lovelace"
    assert len(resume.experience) == 1
    assert resume.skills == ["Mathematics", "Writing"]


def test_resume_json_rejects_wrong_types() -> None:
    with pytest.raises(ValidationError):
        ResumeJSON.model_validate({"skills": "not-a-list"})
