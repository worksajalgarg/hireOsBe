"""Primary document parse via Docling."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path


class DoclingParseError(RuntimeError):
    """Raised when Docling cannot parse the document."""


@dataclass
class ParsedDocument:
    markdown: str
    tables: list[str] = field(default_factory=list)
    source: str = "docling"


def _parse_sync(path: Path) -> ParsedDocument:
    try:
        from docling.document_converter import DocumentConverter
    except ImportError as exc:
        raise DoclingParseError(
            "docling is not installed. Install ai-service requirements."
        ) from exc

    try:
        converter = DocumentConverter()
        result = converter.convert(str(path))
        doc = result.document
        markdown = doc.export_to_markdown()
        tables: list[str] = []
        # Best-effort table extraction; Docling versions differ in API surface.
        try:
            for table in getattr(doc, "tables", []) or []:
                if hasattr(table, "export_to_markdown"):
                    tables.append(table.export_to_markdown())
                else:
                    tables.append(str(table))
        except Exception:
            tables = []

        if not (markdown or "").strip():
            raise DoclingParseError("Docling returned empty markdown")

        return ParsedDocument(markdown=markdown, tables=tables, source="docling")
    except DoclingParseError:
        raise
    except Exception as exc:
        raise DoclingParseError(f"Docling failed: {exc}") from exc


async def parse_with_docling(path: Path) -> ParsedDocument:
    return await asyncio.to_thread(_parse_sync, path)
