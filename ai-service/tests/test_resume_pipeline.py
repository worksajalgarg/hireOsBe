"""Pipeline contract tests without loading Docling or a real model."""

from __future__ import annotations

import asyncio

from app.agents.resume_extractor.docling_parser import ParsedDocument
from app.agents.resume_extractor.pipeline import run_extraction_pipeline
from app.agents.resume_extractor.schemas import ResumeJSON, StageName, StageStatus
from app.agents.resume_extractor.service import ExtractionResult


def test_pdf_pipeline_emits_complete_strict_json(monkeypatch) -> None:
    async def fake_docling(_path):
        return ParsedDocument(
            markdown=(
                "Ada Lovelace\n\nExperience\n\nEngineer, Example Co, 2020-Present\n\n"
                "Education\n\nBSc Mathematics\n\nSkills\n\nPython, PostgreSQL"
            ),
            source="docling",
            meta={"pages": 1},
        )

    async def fake_extract(text, *, parse_source, used_ocr_fallback):
        assert "Example Co" in text
        resume = ResumeJSON.model_validate(
            {
                "contact": {"full_name": "Ada Lovelace"},
                "experience": [
                    {
                        "company": "Example Co",
                        "title": "Engineer",
                        "start_date": "2020",
                        "end_date": "Present",
                        "is_current": True,
                        "evidence": [
                            {
                                "quote": "Engineer, Example Co, 2020-Present",
                                "section": "Experience",
                            }
                        ],
                    }
                ],
                "education": [{"degree": "BSc", "field": "Mathematics"}],
                "skills": ["Python", "PostgreSQL"],
            }
        )
        resume.extraction_metadata.parse_source = parse_source
        resume.extraction_metadata.used_ocr_fallback = used_ocr_fallback
        return ExtractionResult(
            resume=resume,
            raw_json="not-forwarded-to-client",
            provider="test-provider",
            model_name="test-model",
            fallback_used=False,
            chunk_count=1,
        )

    monkeypatch.setattr(
        "app.agents.resume_extractor.pipeline.parse_with_docling", fake_docling
    )
    monkeypatch.setattr(
        "app.agents.resume_extractor.pipeline.extract_resume_json", fake_extract
    )

    async def collect():
        return [
            event
            async for event in run_extraction_pipeline(
                filename="resume.pdf",
                content_type="application/pdf",
                file_bytes=b"%PDF-1.7\nmock",
            )
        ]

    events = asyncio.run(collect())
    final = next(event for event in events if event.stage == StageName.FINAL_JSON)
    assert final.status == StageStatus.SUCCESS
    assert final.data["resume"]["schema_version"] == "2.0"
    assert len(final.data["resume"]["experience"]) == 1
    assert final.data["resume"]["skills"] == ["Python", "PostgreSQL"]

    llm_event = next(event for event in events if event.stage == StageName.LLM_EXTRACTION)
    assert "raw_json" not in llm_event.data
    docling_event = next(
        event
        for event in events
        if event.stage == StageName.DOCLING and event.status == StageStatus.SUCCESS
    )
    assert "markdown_preview" not in docling_event.data
