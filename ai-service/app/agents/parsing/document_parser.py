"""Format-detecting text extraction for resume/JD uploads.

DOCX (and the other declarative formats below) go through docling's
backends directly, NOT `docling.document_converter.DocumentConverter` —
that module's top-level import chain unconditionally pulls in the full
pipeline factory registry (ASR/audio transcription, OCR factories, etc.)
regardless of `allowed_formats`. Calling the backend directly bypasses that
orchestration layer entirely and only needs each format's own extras, not
the full PDF/image pipeline's dependencies.

PDF has two engines behind a feature flag (`PDF_PARSER_ENGINE` env var,
see `pdf_engine()`):

- **docling** (`docling_adapter.parse_pdf_with_docling`) — real layout
  analysis and reading-order reconstruction. Confirmed necessary in
  practice, not a theoretical nicety: pypdfium2's raw content-stream text
  order can diverge badly from visual reading order on templated/
  absolutely-positioned resumes (a real one had two section captions
  extracted as orphaned lines at the very end of the document, nowhere
  near the content they captioned — no amount of prompt tuning or
  text-proximity backfill downstream could recover that, since the
  information was already lost at this layer). Costs real weight (torch +
  docling-ibm-models, ~500MB+) — see requirements-api.txt's comment.
- **pypdfium2** (`parse_pdf` below) — the original, lighter engine. Kept
  as the fallback/rollback path, not deleted, per the migration's own
  "don't remove until proven unnecessary" principle. Extracts embedded
  text directly with no ML model, but in raw content-stream order (see
  above) and with no OCR.

Both engines only handle a PDF's embedded text layer via their respective
paths (docling's OCR is conditional — see docling_adapter.py's docstring —
pypdfium2 has none at all); a page with no usable text degrades to a
near-empty extraction either way, and callers
(resume_intelligence.py/role_intelligence.py) turn that into a 422 before
ever calling the LLM, not a silent bad extraction.

Images (PNG/JPG/JPEG/TIFF/WebP/BMP) have no declarative backend — they go
through docling_adapter.py's same DocumentConverter singleton as PDF (one
converter instance serves both InputFormat.PDF and InputFormat.IMAGE,
confirmed directly — no second ~500MB+ model load), since there's no
embedded text layer to read and OCR is the only way in.

HTML/Markdown/AsciiDoc/ODT are declarative like DOCX (no ML pipeline) —
`_parse_via_declarative_backend` is the one shared implementation all five
(including DOCX) call into, since they're otherwise near-identical.
Confirmed directly against docling 2.118.1: HTML/Markdown/AsciiDoc's
backends are lenient by design (`is_valid()` returns True even on binary
garbage, and non-UTF-8 bytes get decoded some other way rather than
raising — permissive text formats, not strict binary containers like
DOCX/PDF), so there's no realistic "corrupt HTML/MD/AsciiDoc" ParsingError
case the way there is for PDF/DOCX/ODT.

Legacy .doc (binary Word 97-2004) is NOT supported — docling's own
MsWordDocumentBackend converts it via LibreOffice first, a system-level
dependency (not a pip package), unlike every format below. Deferred until
there's a confirmed deploy target that has LibreOffice installed.

parse_docx/parse_pdf/docling_adapter all lazy-import their backend inside
the function body, not at module load, so the voice-worker process and
every non-parsing route never pay any parsing library's import cost — see
app/model_gateway/providers.py's `from google import genai` for the same
pattern already used in this codebase.
"""

import io
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .errors import ParsingError, UnsupportedFileTypeError

logger = logging.getLogger("document_parser")

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".webp", ".bmp"}
_DECLARATIVE_EXTENSIONS = {".html", ".htm", ".md", ".markdown", ".adoc", ".asciidoc", ".odt"}
_SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", *_DECLARATIVE_EXTENSIONS, *_IMAGE_EXTENSIONS}

# Below this chars-per-page ratio, a "successful" extraction is more likely
# a page that genuinely had little text to extract (e.g. a scanned page
# docling's OCR still only partially recovered) — visibility only, not a
# blocking gate; see parse_document's warning below.
_MIN_CHARS_PER_PAGE_WARNING_THRESHOLD = 40


@dataclass(frozen=True)
class ParsedDocument:
    text: str
    source_filename: str
    char_count: int
    # Additive-only fields (both default so every existing call site and
    # test keeps working unmodified) — a hook for the docling engine's
    # quality signal, not yet consumed by resume_intelligence.py/
    # role_intelligence.py beyond the warning logged in parse_document.
    used_ocr: bool = False
    page_count: int | None = None


def _parse_via_declarative_backend(
    data: bytes, filename: str, fmt: object, backend_cls: type, format_label: str
) -> ParsedDocument:
    """Shared by every format with a declarative (no-ML-pipeline) docling
    backend — DOCX, HTML, Markdown, AsciiDoc, ODT all follow this exact
    shape (InputDocument + backend + is_valid + convert), confirmed
    directly against docling 2.118.1. Each caller does its own lazy import
    of fmt/backend_cls (see module docstring's lazy-import discipline) and
    passes them in here rather than this helper importing them itself, so
    this one function doesn't need to know about every format's import
    path."""
    from docling.datamodel.document import InputDocument

    buf = io.BytesIO(data)
    try:
        in_doc = InputDocument(
            path_or_stream=buf, format=fmt, backend=backend_cls, filename=filename
        )
        backend = backend_cls(in_doc, buf)
        if not backend.is_valid():
            raise ParsingError(f"invalid or corrupt {format_label}: {filename}")
        text = backend.convert().export_to_text()
    except ParsingError:
        raise
    except Exception as exc:
        raise ParsingError(f"could not parse {format_label} {filename}: {exc}") from exc
    return ParsedDocument(text=text, source_filename=filename, char_count=len(text))


def parse_docx(data: bytes, filename: str) -> ParsedDocument:
    from docling.backend.msword_backend import MsWordDocumentBackend
    from docling.datamodel.base_models import InputFormat

    return _parse_via_declarative_backend(
        data, filename, InputFormat.DOCX, MsWordDocumentBackend, "docx"
    )


def parse_html(data: bytes, filename: str) -> ParsedDocument:
    from docling.backend.html_backend import HTMLDocumentBackend
    from docling.datamodel.base_models import InputFormat

    return _parse_via_declarative_backend(
        data, filename, InputFormat.HTML, HTMLDocumentBackend, "html"
    )


def parse_markdown(data: bytes, filename: str) -> ParsedDocument:
    from docling.backend.md_backend import MarkdownDocumentBackend
    from docling.datamodel.base_models import InputFormat

    return _parse_via_declarative_backend(
        data, filename, InputFormat.MD, MarkdownDocumentBackend, "markdown"
    )


def parse_asciidoc(data: bytes, filename: str) -> ParsedDocument:
    from docling.backend.asciidoc_backend import AsciiDocBackend
    from docling.datamodel.base_models import InputFormat

    return _parse_via_declarative_backend(
        data, filename, InputFormat.ASCIIDOC, AsciiDocBackend, "asciidoc"
    )


def parse_odt(data: bytes, filename: str) -> ParsedDocument:
    from docling.backend.opendocument_backend import OdtDocumentBackend
    from docling.datamodel.base_models import InputFormat

    return _parse_via_declarative_backend(
        data, filename, InputFormat.ODT, OdtDocumentBackend, "odt"
    )


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


def pdf_engine() -> Literal["docling", "pypdfium2"]:
    """PDF_PARSER_ENGINE env var — defaults to docling as of this session:
    validated end-to-end against real resumes (Khusmuddin/Brandon/Satyam),
    fixing a confirmed reading-order data-loss bug pypdfium2 has on
    templated/multi-column PDFs, with no regression on resumes that already
    worked. pypdfium2 stays available and is one env var away
    (PDF_PARSER_ENGINE=pypdfium2) — see requirements.txt's comment before
    deploying docling to a memory-constrained target (~500MB+ heavier).
    Only an exact "pypdfium2" opts out — unset or any other/malformed
    value (a typo, say) collapses to the same new default rather than
    raising, so a bad env var can't break parsing."""
    value = (os.environ.get("PDF_PARSER_ENGINE") or "docling").strip().lower()
    return "pypdfium2" if value == "pypdfium2" else "docling"


def _warn_if_sparse(parsed: ParsedDocument, filename: str) -> None:
    """Visibility only, not a blocking gate — a genuinely short resume/JD
    legitimately having little text on a page is possible; this is for
    spotting a likely scanned/low-quality source in logs, not for rejecting
    the upload. See resume_intelligence.py's separate _is_suspiciously_empty
    for the actual gate on the LLM's output. Shared by both PDF and image
    dispatch below — both come from docling_adapter and carry a real
    page_count."""
    if (
        parsed.page_count
        and parsed.page_count > 0
        and parsed.char_count / parsed.page_count < _MIN_CHARS_PER_PAGE_WARNING_THRESHOLD
    ):
        logger.warning(
            "parse_document: %d chars across %d page(s) for %s — unusually "
            "sparse extraction, possibly a scanned or low-quality source",
            parsed.char_count, parsed.page_count, filename,
        )


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
            f"supported types: {', '.join(sorted(_SUPPORTED_EXTENSIONS))}"
        )

    if extension == ".docx":
        return parse_docx(data, filename)
    if extension == ".txt":
        return parse_txt(data, filename)
    if extension in {".html", ".htm"}:
        return parse_html(data, filename)
    if extension in {".md", ".markdown"}:
        return parse_markdown(data, filename)
    if extension in {".adoc", ".asciidoc"}:
        return parse_asciidoc(data, filename)
    if extension == ".odt":
        return parse_odt(data, filename)

    if extension in _IMAGE_EXTENSIONS:
        from .docling_adapter import parse_image_with_docling

        parsed = parse_image_with_docling(data, filename)
        _warn_if_sparse(parsed, filename)
        return parsed

    if pdf_engine() == "docling":
        from .docling_adapter import parse_pdf_with_docling

        parsed = parse_pdf_with_docling(data, filename)
    else:
        parsed = parse_pdf(data, filename)

    _warn_if_sparse(parsed, filename)
    return parsed
