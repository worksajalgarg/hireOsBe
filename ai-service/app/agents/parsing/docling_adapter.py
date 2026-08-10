"""Docling-backed PDF and image extraction — reading-order-correct for PDF,
unlike pypdfium2's `get_text_range()` (content-stream order, not visual
order; see parse_pdf's docstring in document_parser.py). Isolated in its
own module so docling's DocumentConverter/pipeline-options API never leaks
past this file — callers only see `ParsedDocument`, same contract
`parse_pdf` already returns.

Confirmed necessary in practice, not theoretical: a real templated resume
(absolutely-positioned sidebar + main column, small italic sub-captions) had
two caption labels ("Courses", "Achievements") extracted by pypdfium2 as
orphaned lines at the very end of the document, nowhere near the bullets
they actually caption — no prompt fix or text-proximity backfill downstream
could recover content that was already lost at this layer. Re-running the
same file through this adapter puts both captions immediately before their
real content, because docling's pipeline does real layout analysis instead
of trusting the PDF's internal content-stream order.

do_ocr=True does not mean "run OCR on every page" — docling's own per-page
text-coverage heuristic decides whether a page actually needs OCR before
invoking it, so a normal text-layer PDF (the common case here) never pays
that cost. This is why there's no separate pre-classification step before
calling this adapter, matching the "don't build an expensive classifier
up front" principle.

Images (PNG/JPG/JPEG/TIFF/WebP/BMP) have no embedded text layer at all —
OCR is the only way in, so parse_image_with_docling always exercises it
(confirmed directly: used_ocr comes out True for a real synthetic image,
via the exact same result.confidence signal parse_pdf_with_docling uses,
no special-casing needed). Shares the same converter singleton as PDF —
confirmed directly that one DocumentConverter instance can serve both
InputFormat.PDF and InputFormat.IMAGE via one format_options dict, so
adding images doesn't cost a second ~500MB+ model load.
"""

import io
import math
import threading
from typing import Any

from .document_parser import ParsedDocument
from .errors import ParsingError

# Constructing DocumentConverter loads real model weights (docling-ibm-models'
# layout model + RapidOCR's ONNX sessions) into memory — confirmed expensive
# in practice, not just in theory: profiled at ~22-31s on a cold process and
# still ~6-7s per call when rebuilt fresh every time (as this module
# originally did), dropping to ~3.3s once a *single* instance is reused
# across calls. A per-request DocumentConverter was silently re-paying that
# reload cost on every single resume/JD upload — this cache is the fix.
# Lock-guarded lazy init: multiple concurrent first-requests (this runs via
# asyncio.to_thread, so genuinely concurrent OS threads are possible) must
# not race to construct two separate converters simultaneously.
_converter_lock = threading.Lock()
_converter: Any = None


def _get_converter() -> Any:
    global _converter
    if _converter is not None:
        return _converter
    with _converter_lock:
        if _converter is None:  # re-check: another thread may have won the race
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import (
                DocumentConverter,
                ImageFormatOption,
                PdfFormatOption,
            )

            pipeline_options = PdfPipelineOptions(do_ocr=True, do_table_structure=True)
            _converter = DocumentConverter(
                allowed_formats=[InputFormat.PDF, InputFormat.IMAGE],
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
                    InputFormat.IMAGE: ImageFormatOption(pipeline_options=pipeline_options),
                },
            )
    return _converter


def _build_warmup_pdf_bytes() -> bytes:
    """A minimal, hand-built single-blank-page PDF — no reportlab (that's a
    dev-only dependency, see requirements-dev.txt, not available at
    production runtime) and no binary asset file committed to the repo
    (matches this project's existing "don't commit binary fixtures"
    convention — see conftest.py's synthetic_pdf_bytes). Just enough valid
    PDF structure (correct xref byte offsets) for pypdfium2/docling-parse
    to open it without error; confirmed directly against both."""
    objects = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]/Resources<<>>>>",
    ]
    buf = io.BytesIO()
    buf.write(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(buf.tell())
        buf.write(f"{i} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref_offset = buf.tell()
    n = len(objects) + 1
    buf.write(f"xref\n0 {n}\n".encode())
    buf.write(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        buf.write(f"{off:010d} 00000 n \n".encode())
    buf.write(f"trailer<</Size {n}/Root 1 0 R>>\nstartxref\n{xref_offset}\n%%EOF".encode())
    return buf.getvalue()


def warm_up() -> None:
    """Pays the cold-start model-load cost once, at service startup, instead
    of on whichever user's request happens to arrive first — see
    app/main.py's lifespan, which calls this only when PDF_PARSER_ENGINE is
    actually docling. Best-effort: a failure here shouldn't be fatal to
    service startup, since the first real request will just retry the
    (expensive) construction anyway.

    Constructing DocumentConverter alone is NOT enough — confirmed directly
    by profiling: DocumentConverter(...) itself only takes ~2s, because
    docling's actual model weights (layout model, RapidOCR's ONNX sessions)
    load lazily on the first real .convert() call, not at construction.
    Calling only _get_converter() here (the original version of this
    function) meant "warm-up" silently warmed nothing — the first real
    resume upload still paid the full ~20s cold-load cost. Running one real
    conversion against a trivial in-memory PDF forces that lazy load to
    happen now, at startup, using the exact same code path
    parse_pdf_with_docling uses for real requests."""
    parse_pdf_with_docling(_build_warmup_pdf_bytes(), "warmup.pdf")


def _convert_and_wrap(data: bytes, filename: str, format_label: str) -> ParsedDocument:
    """Shared by parse_pdf_with_docling and parse_image_with_docling — both
    go through the same singleton converter and the same result shape
    (result.document, result.confidence), so the conversion + error
    handling + used_ocr/page_count extraction only needs writing once."""
    from docling.exceptions import ConversionError
    from docling_core.types.io import DocumentStream

    converter = _get_converter()

    try:
        stream = DocumentStream(name=filename, stream=io.BytesIO(data))
        result = converter.convert(stream)
    except ConversionError as exc:
        raise ParsingError(f"could not parse {format_label} {filename}: {exc}") from exc
    except Exception as exc:
        # docling/docling-parse can raise its own lower-level exceptions
        # (not always wrapped in ConversionError) for a genuinely corrupt
        # or unsupported file — treat any conversion failure the same way
        # parse_pdf (pypdfium2 path) does: a 422-worthy ParsingError, not a
        # 500 that leaks an internal stack trace to the caller.
        raise ParsingError(f"could not parse {format_label} {filename}: {exc}") from exc

    text = result.document.export_to_text()
    page_count = len(result.document.pages) if result.document.pages else None

    # result.confidence.pages[n].ocr_score defaults to NaN and is only set
    # by docling's OCR model when that page actually produced OCR'd cells
    # (docling/models/base_ocr_model.py) — confirmed by reading the source,
    # not assumed. A non-NaN score on any page means OCR genuinely ran on
    # this document, not just that do_ocr=True was configured. Images have
    # no embedded text layer at all, so this comes out True for them with
    # no special-casing needed — confirmed directly against a synthetic
    # image.
    used_ocr = any(not math.isnan(score.ocr_score) for score in result.confidence.pages.values())

    return ParsedDocument(
        text=text,
        source_filename=filename,
        char_count=len(text),
        used_ocr=used_ocr,
        page_count=page_count,
    )


def parse_pdf_with_docling(data: bytes, filename: str) -> ParsedDocument:
    return _convert_and_wrap(data, filename, "pdf")


def parse_image_with_docling(data: bytes, filename: str) -> ParsedDocument:
    return _convert_and_wrap(data, filename, "image")
