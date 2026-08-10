"""Primary document parse via Docling (layout/OCR/tables — not an LLM)."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import get_settings

# Cap JSON snippet size in SSE / ParsedDocument (full doc can be huge).
_DOCUMENT_JSON_PREVIEW_CHARS = 12_000


class DoclingParseError(RuntimeError):
    """Raised when Docling cannot parse the document."""


@dataclass
class ParsedDocument:
    markdown: str
    tables: list[str] = field(default_factory=list)
    source: str = "docling"
    document_json_preview: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


def _build_pdf_pipeline_options():
    from docling.datamodel.pipeline_options import (
        PdfPipelineOptions,
        RapidOcrOptions,
        TableFormerMode,
        TableStructureOptions,
    )

    settings = get_settings()
    return PdfPipelineOptions(
        do_ocr=True,
        do_table_structure=True,
        do_picture_description=False,
        do_picture_classification=False,
        do_chart_extraction=False,
        do_code_enrichment=False,
        do_formula_enrichment=False,
        force_backend_text=False,
        table_structure_options=TableStructureOptions(
            do_cell_matching=True,
            mode=TableFormerMode.ACCURATE,
        ),
        ocr_options=RapidOcrOptions(
            lang=["en"],
            force_full_page_ocr=settings.docling_force_full_page_ocr,
        ),
    )


@lru_cache(maxsize=1)
def _get_converter():
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import ConvertPipelineOptions
    from docling.document_converter import (
        DocumentConverter,
        HTMLFormatOption,
        ImageFormatOption,
        MarkdownFormatOption,
        OdtFormatOption,
        PdfFormatOption,
        WordFormatOption,
    )

    pdf_opts = _build_pdf_pipeline_options()
    simple_opts = ConvertPipelineOptions(
        do_picture_description=False,
        do_picture_classification=False,
        do_chart_extraction=False,
    )
    # Resume-oriented Docling formats (aligned with formats.ALLOWED_EXTENSIONS).
    allowed = [
        InputFormat.PDF,
        InputFormat.DOCX,
        InputFormat.DOC,
        InputFormat.ODT,
        InputFormat.HTML,
        InputFormat.MD,
        InputFormat.ASCIIDOC,
        InputFormat.IMAGE,
    ]
    return DocumentConverter(
        allowed_formats=allowed,
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_opts),
            InputFormat.DOCX: WordFormatOption(pipeline_options=simple_opts),
            InputFormat.DOC: WordFormatOption(pipeline_options=simple_opts),
            InputFormat.ODT: OdtFormatOption(pipeline_options=simple_opts),
            InputFormat.HTML: HTMLFormatOption(pipeline_options=simple_opts),
            InputFormat.MD: MarkdownFormatOption(pipeline_options=simple_opts),
            InputFormat.IMAGE: ImageFormatOption(pipeline_options=pdf_opts),
        },
    )


def _export_tables(doc: Any) -> list[str]:
    tables: list[str] = []
    for table in getattr(doc, "tables", []) or []:
        md = ""
        if hasattr(table, "export_to_markdown"):
            try:
                md = (table.export_to_markdown(doc=doc) or "").strip()
            except Exception:
                md = ""
        if not md and hasattr(table, "export_to_dataframe"):
            try:
                df = table.export_to_dataframe(doc=doc)
                md = (df.to_markdown(index=False) or "").strip()
            except Exception:
                md = ""
        if md:
            tables.append(md)
    return tables


def _document_json_preview(doc: Any) -> str:
    try:
        payload = doc.export_to_dict(mode="json", exclude_none=True)
    except Exception:
        try:
            payload = doc.model_dump(mode="json", exclude_none=True)
        except Exception:
            return ""

    # Drop heavy binary/image payloads if present; keep layout/text structure.
    if isinstance(payload, dict):
        for heavy_key in ("pictures", "page_images", "key_value_items"):
            if heavy_key in payload and isinstance(payload[heavy_key], list):
                payload[heavy_key] = f"[{len(payload[heavy_key])} items omitted]"

    try:
        raw = json.dumps(payload, ensure_ascii=False, default=str)
    except Exception:
        raw = str(payload)

    if len(raw) <= _DOCUMENT_JSON_PREVIEW_CHARS:
        return raw
    return raw[:_DOCUMENT_JSON_PREVIEW_CHARS] + "…[truncated]"


def _pipeline_meta() -> dict[str, Any]:
    settings = get_settings()
    return {
        "do_ocr": True,
        "do_table_structure": True,
        "table_mode": "accurate",
        "ocr_engine": "rapidocr",
        "ocr_lang": ["en"],
        "force_full_page_ocr": settings.docling_force_full_page_ocr,
        "picture_description": False,
    }


def _parse_sync(path: Path) -> ParsedDocument:
    try:
        from docling.document_converter import DocumentConverter  # noqa: F401
    except ImportError as exc:
        raise DoclingParseError(
            "docling is not installed. Install ai-service requirements."
        ) from exc

    try:
        converter = _get_converter()
        result = converter.convert(str(path))
        doc = result.document

        markdown = (
            doc.export_to_markdown(
                page_break_placeholder="\n\n---\n\n",
                include_annotations=True,
                compact_tables=False,
                enable_chart_tables=True,
            )
            or ""
        ).strip()

        tables = _export_tables(doc)
        # Full Docling JSON is intentionally not copied into progress events. The
        # normalized markdown and structured resume are the retained artifacts.
        json_preview = ""
        pages = None
        num_pages = getattr(doc, "num_pages", None)
        if callable(num_pages):
            try:
                pages = int(num_pages())
            except Exception:
                pages = None
        elif isinstance(num_pages, int):
            pages = num_pages
        if pages is None:
            page_list = getattr(doc, "pages", None) or []
            try:
                pages = len(page_list) or None
            except Exception:
                pages = None

        meta = {
            **_pipeline_meta(),
            "table_count": len(tables),
            "markdown_length": len(markdown),
            "has_document_json_preview": bool(json_preview),
            "pages": pages,
        }

        if not markdown:
            raise DoclingParseError("Docling returned empty markdown")

        return ParsedDocument(
            markdown=markdown,
            tables=tables,
            source="docling",
            document_json_preview=json_preview,
            meta=meta,
        )
    except DoclingParseError:
        raise
    except Exception as exc:
        raise DoclingParseError(f"Docling failed: {exc}") from exc


async def parse_with_docling(path: Path) -> ParsedDocument:
    return await asyncio.to_thread(_parse_sync, path)
