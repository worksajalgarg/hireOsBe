"""Unit tests for resume extractor validation, normalize, and schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agents.resume_extractor.normalize import normalize_text
from app.agents.resume_extractor.schemas import ResumeJSON
from app.agents.resume_extractor.service import (
    _parse_json_object,
    merge_resume_chunks,
    split_resume_text,
)
from app.agents.resume_extractor.validation import (
    FileValidationError,
    validate_file_signature,
    validate_upload,
)


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


def test_validate_upload_sanitizes_paths_and_rejects_bad_mime() -> None:
    result = validate_upload(
        filename="../../private/Jane_Doe.pdf",
        content_type="application/pdf",
        size_bytes=100,
    )
    assert result.filename == "Jane_Doe.pdf"

    with pytest.raises(FileValidationError, match="content type"):
        validate_upload(
            filename="resume.pdf",
            content_type="application/x-msdownload",
            size_bytes=100,
        )


def test_validate_pdf_signature_rejects_renamed_binary() -> None:
    with pytest.raises(FileValidationError, match="valid PDF"):
        validate_file_signature(extension=".pdf", file_bytes=b"MZ-not-a-pdf")
    validate_file_signature(extension=".pdf", file_bytes=b"%PDF-1.7\n")


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
        "languages": [{"name": "English", "proficiency": None}],
    }
    resume = ResumeJSON.model_validate(payload)
    assert resume.contact.full_name == "Ada Lovelace"
    assert len(resume.experience) == 1
    assert resume.skills == ["Mathematics", "Writing"]


def test_resume_json_rejects_unknown_model_fields() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ResumeJSON.model_validate({"personality": "outgoing"})


def test_resume_json_rejects_wrong_types() -> None:
    with pytest.raises(ValidationError):
        ResumeJSON.model_validate({"skills": "not-a-list"})


def test_incomplete_json_is_not_repaired() -> None:
    with pytest.raises(ValueError, match="incomplete JSON"):
        _parse_json_object('{"contact":{"full_name":"Ada"}')


def test_chunking_preserves_complete_source() -> None:
    source = "\n\n".join(f"Section {i}: " + ("x" * 80) for i in range(12))
    chunks = split_resume_text(source, max_chars=220, max_chunks=20)
    assert len(chunks) > 1
    assert "".join(chunks).replace("\n", "") == source.replace("\n", "")


def test_merge_keeps_all_roles_and_deduplicates_overlap() -> None:
    first = ResumeJSON.model_validate(
        {
            "experience": [
                {
                    "company": "Example",
                    "title": "Engineer",
                    "start_date": "2020",
                    "end_date": "2022",
                    "highlights": ["Built API"],
                }
            ],
            "skills": ["Python"],
        }
    )
    second = ResumeJSON.model_validate(
        {
            "experience": [
                {
                    "company": "Example",
                    "title": "Engineer",
                    "start_date": "2020",
                    "end_date": "2022",
                    "highlights": ["Built API", "Led migration"],
                },
                {
                    "company": "Next Co",
                    "title": "Senior Engineer",
                    "start_date": "2022",
                    "end_date": None,
                },
            ],
            "skills": ["Python", "PostgreSQL"],
        }
    )
    merged = merge_resume_chunks([first, second])
    assert len(merged.experience) == 2
    assert merged.experience[0].highlights == ["Built API", "Led migration"]
    assert merged.skills == ["Python", "PostgreSQL"]
