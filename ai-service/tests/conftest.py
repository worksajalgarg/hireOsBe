from pathlib import Path

import pytest

from app.model_gateway.routing_config import load_routing_config
from app.model_gateway.use_case_policy import USE_CASE_POLICIES

_ROUTING_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "model_routing.yaml"


@pytest.fixture(autouse=True, scope="session")
def _load_real_routing_config() -> None:
    """USE_CASE_POLICIES starts empty (see use_case_policy.py) and is
    normally populated at process startup by worker.py/main.py. Tests that
    call get_policy()/apply_provider_priority() against real use-case names
    (e.g. test_use_case_policy_priority.py) need it populated the same way
    production is, from the real config/model_routing.yaml — not a fixture
    file, so those tests keep asserting against actual production chains."""
    USE_CASE_POLICIES.update(load_routing_config(_ROUTING_CONFIG_PATH))


@pytest.fixture(scope="session")
def synthetic_docx_bytes() -> bytes:
    """A minimal, entirely synthetic .docx generated in-memory — never a
    real resume/JD, given this project's strict candidate-PII posture (see
    docs/adr/0007-no-pydantic-ai-for-structured-extraction.md's sibling
    parsing work). Not written to disk or committed — regenerated per test
    session so there's no binary fixture to accidentally mistake for real
    data."""
    import io

    import docx

    doc = docx.Document()
    doc.add_heading("Test Candidate", level=1)
    doc.add_paragraph("Placeholder Engineer with 5 years of made-up experience.")
    doc.add_heading("Experience", level=2)
    doc.add_paragraph("Example Corp — Placeholder Engineer (2021-Present): Did placeholder work.")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest.fixture(scope="session")
def synthetic_pdf_bytes() -> bytes:
    """A minimal, entirely synthetic .pdf generated in-memory — same
    synthetic-only rationale as synthetic_docx_bytes above."""
    import io

    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 750, "Test Candidate")
    c.drawString(72, 730, "Placeholder Engineer with 5 years of made-up experience.")
    c.drawString(72, 710, "Experience: Example Corp - Placeholder Engineer (2021-Present)")
    c.save()
    return buf.getvalue()


@pytest.fixture(scope="session")
def synthetic_scanned_pdf_bytes() -> bytes:
    """A PDF with no real text layer at all — the page content is a
    rasterized image of text, not embedded text objects — so it genuinely
    exercises docling's OCR path rather than its normal text-extraction
    path. Confirms parse_pdf_with_docling's used_ocr signal against a real
    "scanned document" case, not a mock."""
    import io

    from PIL import Image, ImageDraw
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    img = Image.new("RGB", (600, 200), "white")
    ImageDraw.Draw(img).text((10, 80), "Scanned Placeholder Text", fill="black")
    img_buf = io.BytesIO()
    img.save(img_buf, format="PNG")
    img_buf.seek(0)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(600, 200))
    c.drawImage(ImageReader(img_buf), 0, 0, width=600, height=200)
    c.save()
    return buf.getvalue()


@pytest.fixture(scope="session")
def synthetic_html_bytes() -> bytes:
    """Plain text is enough — the html_backend test only needs to confirm
    text extraction works, not exercise any layout/table edge case."""
    return (
        b"<html><body><h1>Test Candidate</h1>"
        b"<p>Placeholder Engineer with 5 years of made-up experience.</p>"
        b"</body></html>"
    )


@pytest.fixture(scope="session")
def synthetic_markdown_bytes() -> bytes:
    return (
        b"# Test Candidate\n\n"
        b"Placeholder Engineer with 5 years of made-up experience.\n"
    )


@pytest.fixture(scope="session")
def synthetic_asciidoc_bytes() -> bytes:
    return (
        b"= Test Candidate\n\n"
        b"Placeholder Engineer with 5 years of made-up experience.\n"
    )


@pytest.fixture(scope="session")
def synthetic_odt_bytes() -> bytes:
    """A minimal, entirely synthetic .odt generated in-memory via odfdo —
    same synthetic-only rationale as synthetic_docx_bytes above. odfdo, not
    odfpy: confirmed by reading docling's opendocument_backend.py source
    directly (`from odfdo import ...`) after odfpy turned out to be the
    wrong package name — docling's actual runtime error names odfdo
    explicitly."""
    import io

    from odfdo import Document, Paragraph

    doc = Document("text")
    doc.body.append(Paragraph("Test Candidate"))
    doc.body.append(Paragraph("Placeholder Engineer with 5 years of made-up experience."))
    buf = io.BytesIO()
    doc.save(target=buf)
    return buf.getvalue()


@pytest.fixture(scope="session")
def synthetic_image_bytes() -> bytes:
    """A rasterized PNG with no embedded text layer — same
    Pillow-drawn-text approach as synthetic_scanned_pdf_bytes above, minus
    the PDF wrapper, so it exercises docling's image/OCR path directly."""
    import io

    from PIL import Image, ImageDraw

    img = Image.new("RGB", (600, 200), "white")
    ImageDraw.Draw(img).text((10, 80), "Scanned Placeholder Resume", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
