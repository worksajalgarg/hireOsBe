"""Async pipeline yielding SSE stage events for resume extraction."""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

from app.config import get_settings

from .docling_parser import DoclingParseError, ParsedDocument, parse_with_docling
from .legacy_doc import LegacyDocError, prepare_doc_for_parse
from .normalize import normalize_text
from .ocr_fallback import OcrFallbackError, parse_with_ocr_fallback
from .schemas import StageEvent, StageName, StageStatus
from .service import extract_resume_json
from .validation import FileValidationError, validate_file_signature, validate_upload


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
        validate_file_signature(extension=validated.extension, file_bytes=file_bytes)
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
        parse_path = path
        normalize_meta: dict = {}

        if suffix == ".doc":
            try:
                parse_path = await asyncio.to_thread(
                    prepare_doc_for_parse,
                    path,
                    Path(tmp) / "normalized",
                )
                normalize_meta = {
                    "legacy_doc": True,
                    "normalized_to": parse_path.suffix.lstrip(".").lower(),
                    "normalized_name": parse_path.name,
                }
            except LegacyDocError as exc:
                normalize_meta = {"legacy_doc": True, "normalize_error": str(exc)}

        yield StageEvent(
            stage=StageName.DOCLING,
            status=StageStatus.RUNNING,
            message=(
                "Parsing document with Docling"
                + (
                    f" (normalized .doc → .{normalize_meta.get('normalized_to')})"
                    if normalize_meta.get("normalized_to")
                    else ""
                )
            ),
            data=normalize_meta or {},
        )
        parsed = None
        used_fallback = False
        try:
            if parse_path.suffix.lower() == ".txt":
                text = parse_path.read_text(encoding="utf-8", errors="replace").strip()
                if not text:
                    raise DoclingParseError("Legacy .doc converted to empty text")
                parsed = ParsedDocument(
                    markdown=text,
                    tables=[],
                    source="legacy_doc_textutil",
                    meta={**normalize_meta, "pages": 1},
                )
            else:
                parsed = await parse_with_docling(parse_path)
            yield StageEvent(
                stage=StageName.DOCLING,
                status=StageStatus.SUCCESS,
                message="Docling parse succeeded (layout/OCR/tables; no LLM)",
                data={
                    "markdown_length": len(parsed.markdown),
                    "table_count": len(parsed.tables),
                    "source": parsed.source,
                    "meta": {**parsed.meta, **normalize_meta},
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
                message="Trying legacy-doc / PyMuPDF / EasyOCR fallback",
            )
            try:
                parsed = await parse_with_ocr_fallback(path)
                used_fallback = True
                yield StageEvent(
                    stage=StageName.OCR_FALLBACK,
                    status=StageStatus.SUCCESS,
                    message=f"Fallback succeeded via {parsed.source}",
                    data={
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
            # Append structured table markdown so the LLM sees grid content even if
            # inline markdown omitted a table edge case.
            pieces.append(
                "\n\n## Extracted tables\n\n"
                + "\n\n".join(
                    f"### Table {i + 1}\n\n{table}"
                    for i, table in enumerate(parsed.tables)
                )
            )
        settings = get_settings()
        normalized = normalize_text(
            "\n\n".join(pieces), max_chars=settings.resume_source_max_chars + 1
        )
        if len(normalized) > settings.resume_source_max_chars:
            yield StageEvent(
                stage=StageName.ERROR,
                status=StageStatus.FAILED,
                message=(
                    "Extracted source exceeds configured safety limit of "
                    f"{settings.resume_source_max_chars} characters"
                ),
            )
            return
        yield StageEvent(
            stage=StageName.TEXT_NORMALIZATION,
            status=StageStatus.SUCCESS,
            message="Text normalized for LLM field mapping",
            data={
                "length": len(normalized),
                "used_ocr_fallback": used_fallback,
                "table_count": len(parsed.tables),
                "parse_source": parsed.source,
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
            extraction = await extract_resume_json(
                normalized,
                parse_source=parsed.source,
                used_ocr_fallback=used_fallback,
            )
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
            data={
                "provider": extraction.provider,
                "model": extraction.model_name,
                "chunk_count": extraction.chunk_count,
                "fallback_used": extraction.fallback_used,
            },
        )

        yield StageEvent(
            stage=StageName.PYDANTIC_VALIDATION,
            status=StageStatus.RUNNING,
            message="Validating against ResumeJSON schema",
        )
        yield StageEvent(
            stage=StageName.PYDANTIC_VALIDATION,
            status=StageStatus.SUCCESS,
            message="Schema validation passed",
        )

        final = extraction.resume.model_dump(mode="json")
        yield StageEvent(
            stage=StageName.FINAL_JSON,
            status=StageStatus.SUCCESS,
            message="Resume extraction complete",
            data={"resume": final},
        )
