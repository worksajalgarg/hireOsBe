"""Async pipeline yielding SSE stage events for resume extraction."""

from __future__ import annotations

import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

from .docling_parser import DoclingParseError, parse_with_docling
from .normalize import normalize_text
from .ocr_fallback import OcrFallbackError, parse_with_ocr_fallback
from .schemas import StageEvent, StageName, StageStatus
from .service import extract_resume_json, validate_resume_payload
from .validation import FileValidationError, validate_upload


async def run_extraction_pipeline(
    *,
    filename: str,
    content_type: str | None,
    file_bytes: bytes,
) -> AsyncIterator[StageEvent]:
    yield StageEvent(
        stage=StageName.UPLOAD_RECEIVED,
        status=StageStatus.SUCCESS,
        message=f"Received {filename} ({len(file_bytes)} bytes)",
        data={"filename": filename, "size_bytes": len(file_bytes)},
    )

    yield StageEvent(
        stage=StageName.FILE_VALIDATION,
        status=StageStatus.RUNNING,
        message="Validating file type and size",
    )
    try:
        validated = validate_upload(
            filename=filename,
            content_type=content_type,
            size_bytes=len(file_bytes),
        )
    except FileValidationError as exc:
        yield StageEvent(
            stage=StageName.FILE_VALIDATION,
            status=StageStatus.FAILED,
            message=str(exc),
        )
        yield StageEvent(
            stage=StageName.ERROR,
            status=StageStatus.FAILED,
            message=str(exc),
        )
        return

    yield StageEvent(
        stage=StageName.FILE_VALIDATION,
        status=StageStatus.SUCCESS,
        message="File validation passed",
        data={
            "filename": validated.filename,
            "extension": validated.extension,
            "content_type": validated.content_type,
            "size_bytes": validated.size_bytes,
        },
    )

    suffix = validated.extension
    with tempfile.TemporaryDirectory(prefix="resume_extract_") as tmp:
        path = Path(tmp) / validated.filename
        path.write_bytes(file_bytes)

        yield StageEvent(
            stage=StageName.DOCLING,
            status=StageStatus.RUNNING,
            message="Parsing document with Docling",
        )
        parsed = None
        used_fallback = False
        try:
            parsed = await parse_with_docling(path)
            yield StageEvent(
                stage=StageName.DOCLING,
                status=StageStatus.SUCCESS,
                message="Docling parse succeeded",
                data={
                    "markdown_preview": parsed.markdown[:2000],
                    "markdown_length": len(parsed.markdown),
                    "table_count": len(parsed.tables),
                    "source": parsed.source,
                },
            )
            yield StageEvent(
                stage=StageName.OCR_FALLBACK,
                status=StageStatus.SKIPPED,
                message="OCR fallback not needed",
            )
        except DoclingParseError as exc:
            yield StageEvent(
                stage=StageName.DOCLING,
                status=StageStatus.FAILED,
                message=str(exc),
            )
            yield StageEvent(
                stage=StageName.OCR_FALLBACK,
                status=StageStatus.RUNNING,
                message="Trying PyMuPDF + EasyOCR fallback",
            )
            try:
                parsed = await parse_with_ocr_fallback(path)
                used_fallback = True
                yield StageEvent(
                    stage=StageName.OCR_FALLBACK,
                    status=StageStatus.SUCCESS,
                    message=f"Fallback succeeded via {parsed.source}",
                    data={
                        "markdown_preview": parsed.markdown[:2000],
                        "markdown_length": len(parsed.markdown),
                        "source": parsed.source,
                    },
                )
            except OcrFallbackError as fallback_exc:
                yield StageEvent(
                    stage=StageName.OCR_FALLBACK,
                    status=StageStatus.FAILED,
                    message=str(fallback_exc),
                )
                yield StageEvent(
                    stage=StageName.ERROR,
                    status=StageStatus.FAILED,
                    message=f"Document parse failed: {fallback_exc}",
                )
                return

        assert parsed is not None

        yield StageEvent(
            stage=StageName.TEXT_NORMALIZATION,
            status=StageStatus.RUNNING,
            message="Normalizing extracted text",
        )
        pieces = [parsed.markdown]
        if parsed.tables:
            pieces.append("\n\n## Tables\n\n" + "\n\n".join(parsed.tables))
        normalized = normalize_text("\n\n".join(pieces))
        yield StageEvent(
            stage=StageName.TEXT_NORMALIZATION,
            status=StageStatus.SUCCESS,
            message="Text normalized",
            data={
                "preview": normalized[:2000],
                "length": len(normalized),
                "used_ocr_fallback": used_fallback,
            },
        )

        if not normalized.strip():
            yield StageEvent(
                stage=StageName.ERROR,
                status=StageStatus.FAILED,
                message="Normalized text is empty; cannot extract resume",
            )
            return

        yield StageEvent(
            stage=StageName.LLM_EXTRACTION,
            status=StageStatus.RUNNING,
            message="Calling LLM for structured extraction",
        )
        try:
            raw_json, payload = await extract_resume_json(normalized)
        except Exception as exc:
            yield StageEvent(
                stage=StageName.LLM_EXTRACTION,
                status=StageStatus.FAILED,
                message=str(exc),
            )
            yield StageEvent(
                stage=StageName.ERROR,
                status=StageStatus.FAILED,
                message=f"LLM extraction failed: {exc}",
            )
            return

        yield StageEvent(
            stage=StageName.LLM_EXTRACTION,
            status=StageStatus.SUCCESS,
            message="LLM returned structured JSON",
            data={"raw_json": raw_json[:8000]},
        )

        yield StageEvent(
            stage=StageName.PYDANTIC_VALIDATION,
            status=StageStatus.RUNNING,
            message="Validating against ResumeJSON schema",
        )
        try:
            resume = validate_resume_payload(payload)
        except Exception as exc:
            yield StageEvent(
                stage=StageName.PYDANTIC_VALIDATION,
                status=StageStatus.FAILED,
                message=str(exc),
                data={"raw_payload": payload},
            )
            yield StageEvent(
                stage=StageName.ERROR,
                status=StageStatus.FAILED,
                message=f"Pydantic validation failed: {exc}",
            )
            return

        yield StageEvent(
            stage=StageName.PYDANTIC_VALIDATION,
            status=StageStatus.SUCCESS,
            message="Schema validation passed",
        )

        final = resume.model_dump(mode="json")
        yield StageEvent(
            stage=StageName.FINAL_JSON,
            status=StageStatus.SUCCESS,
            message="Resume extraction complete",
            data={"resume": final},
        )
