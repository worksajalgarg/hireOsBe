"""Format-detecting text extraction for resume/JD uploads.

DOCX goes through docling's DOCX backend directly (`MsWordDocumentBackend`),
NOT `docling.document_converter.DocumentConverter` — that module's top-level
import chain unconditionally pulls in the full pipeline factory registry
(ASR/audio transcription, OCR factories, etc.) regardless of
`allowed_formats`, so it fails to import at all without extras this project
deliberately doesn't install (`docling_parse`, `rtree`, ...). Calling the
backend directly bypasses that orchestration layer entirely and imports
cleanly with just `docling-slim[format-docx]`.

PDF deliberately does NOT go through any docling PDF pipeline — docling has
no PDF backend that is "declarative"; any PDF conversion through docling
unconditionally loads its layout-detection model (torch + docling-ibm-models,
500MB+ install), even with OCR/table-structure disabled. `pypdfium2`
(docling's own underlying PDF library, usable standalone) extracts embedded
text directly with no ML model and no torch dependency.

No OCR: this only handles PDFs/DOCX with an embedded text layer (typical
resumes/JDs exported from a word processor or ATS). A scanned/image-only PDF
degrades to a near-empty extracted_text_length result — callers
(resume_intelligence.py/role_intelligence.py) turn that into a 422, not a
silent bad extraction, before ever calling the LLM.

Both parse_docx/parse_pdf lazy-import their backend inside the function body,
not at module load, so the voice-worker process and every non-parsing route
never pay either library's import cost — see
app/model_gateway/providers.py's `from google import genai` for the same
pattern already used in this codebase.
"""

import io
from dataclasses import dataclass
from pathlib import Path

from .errors import ParsingError, UnsupportedFileTypeError

_SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}


@dataclass(frozen=True)
class ParsedDocument:
    text: str
    source_filename: str
    char_count: int


def parse_docx(data: bytes, filename: str) -> ParsedDocument:
    from docling.backend.msword_backend import MsWordDocumentBackend
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.document import InputDocument

    buf = io.BytesIO(data)
    try:
        in_doc = InputDocument(
            path_or_stream=buf,
            format=InputFormat.DOCX,
            backend=MsWordDocumentBackend,
            filename=filename,
        )
        backend = MsWordDocumentBackend(in_doc, buf)
        if not backend.is_valid():
            raise ParsingError(f"invalid or corrupt docx: {filename}")
        text = backend.convert().export_to_text()
    except ParsingError:
        raise
    except Exception as exc:
        raise ParsingError(f"could not parse docx {filename}: {exc}") from exc
    return ParsedDocument(text=text, source_filename=filename, char_count=len(text))


def parse_pdf(data: bytes, filename: str) -> ParsedDocument:
    import pypdfium2 as pdfium

    try:
        pdf = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as exc:
        raise ParsingError(f"could not parse pdf {filename}: {exc}") from exc

    try:
        parts: list[str] = []
        for page in pdf:
            textpage = page.get_textpage()
            try:
                parts.append(textpage.get_text_range())
            finally:
                textpage.close()
                page.close()
        text = "\n".join(parts)
    except pdfium.PdfiumError as exc:
        raise ParsingError(f"could not parse pdf {filename}: {exc}") from exc
    finally:
        pdf.close()

    return ParsedDocument(text=text, source_filename=filename, char_count=len(text))


def parse_txt(data: bytes, filename: str) -> ParsedDocument:
    """No docling/pypdfium2 involved — platform's "paste JD text" path
    synthesizes a text/plain upload rather than adding a second ai-service
    endpoint for pasted text, so this just needs to decode bytes."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ParsingError(f"could not decode text file {filename}: {exc}") from exc
    return ParsedDocument(text=text, source_filename=filename, char_count=len(text))


def parse_document(data: bytes, filename: str, content_type: str | None) -> ParsedDocument:
    """Dispatches purely on filename extension — content_type is accepted
    for future use (e.g. logging/validation) but not currently trusted,
    since browsers/clients send inconsistent MIME types for the same file."""
    if not data:
        raise ParsingError(f"empty file: {filename}")

    extension = Path(filename).suffix.lower()
    if extension not in _SUPPORTED_EXTENSIONS:
        raise UnsupportedFileTypeError(
            f"unsupported file type '{extension or '(none)'}' for {filename} — "
            "only .pdf, .docx, and .txt are supported"
        )

    if extension == ".docx":
        return parse_docx(data, filename)
    if extension == ".txt":
        return parse_txt(data, filename)
    return parse_pdf(data, filename)
