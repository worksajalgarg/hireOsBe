import io

from fastapi.testclient import TestClient

from app.agents.role_intelligence_schema import RequirementClaim, RoleExtractionLLMOutput
from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/role-intelligence/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_empty_file_returns_422() -> None:
    response = client.post(
        "/role-intelligence/parse", files={"file": ("jd.pdf", b"", "application/pdf")}
    )
    assert response.status_code == 422


def test_unsupported_file_type_returns_415() -> None:
    """.zip, not .png — .png became a supported image extension this
    session (see document_parser.py's _IMAGE_EXTENSIONS)."""
    response = client.post(
        "/role-intelligence/parse", files={"file": ("jd.zip", b"hello", "application/zip")}
    )
    assert response.status_code == 415


def test_near_empty_text_pdf_returns_422_before_calling_gateway(monkeypatch) -> None:
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 750, "Hi")
    c.save()
    near_empty_pdf = buf.getvalue()

    called = False

    async def fake_run_structured(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("should not be called for near-empty extracted text")

    monkeypatch.setattr(
        "app.agents.role_intelligence.model_gateway.run_structured", fake_run_structured
    )

    response = client.post(
        "/role-intelligence/parse", files={"file": ("jd.pdf", near_empty_pdf, "application/pdf")}
    )
    assert response.status_code == 422
    assert called is False


def test_gateway_failure_returns_502(monkeypatch, synthetic_pdf_bytes: bytes) -> None:
    async def fake_run_structured(**kwargs):
        raise RuntimeError("provider chain exhausted")

    monkeypatch.setattr(
        "app.agents.role_intelligence.model_gateway.run_structured", fake_run_structured
    )

    files = {"file": ("jd.pdf", synthetic_pdf_bytes, "application/pdf")}
    response = client.post("/role-intelligence/parse", files=files)
    assert response.status_code == 502


def test_empty_extraction_on_substantial_jd_returns_502(monkeypatch) -> None:
    """model_gateway.run_structured only validates JSON shape — a
    schema-valid but fully empty result on a real, lengthy JD must not be
    persisted as a success. Confirmed necessary in practice: a free-tier
    model returned exactly this shape for a real ~500-word JD."""
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    # Comfortably over MIN_CHARS_FOR_EMPTY_CHECK (300, in document_intake_limits.py).
    for i in range(12):
        c.drawString(72, 750 - i * 20, f"Requirement line number {i} of the job description.")
    c.save()
    long_pdf = buf.getvalue()

    async def fake_run_structured(**kwargs):
        return RoleExtractionLLMOutput()  # everything empty, no unparsed_sections either

    monkeypatch.setattr(
        "app.agents.role_intelligence.model_gateway.run_structured", fake_run_structured
    )

    response = client.post(
        "/role-intelligence/parse", files={"file": ("jd.pdf", long_pdf, "application/pdf")}
    )
    assert response.status_code == 502


def test_happy_path_returns_structured_extraction(monkeypatch, synthetic_pdf_bytes: bytes) -> None:
    fake_output = RoleExtractionLLMOutput(
        role_title="Placeholder Engineer",
        must_have_requirements=[
            RequirementClaim(
                requirement="5 years experience", source_text="5 years of made-up experience"
            )
        ],
    )

    async def fake_run_structured(**kwargs):
        assert kwargs["use_case"] == "role_parsing"
        return fake_output

    monkeypatch.setattr(
        "app.agents.role_intelligence.model_gateway.run_structured", fake_run_structured
    )

    files = {"file": ("jd.pdf", synthetic_pdf_bytes, "application/pdf")}
    response = client.post("/role-intelligence/parse", files=files)
    assert response.status_code == 200
    body = response.json()
    assert body["role_title"] == "Placeholder Engineer"
    assert body["must_have_requirements"][0]["requirement"] == "5 years experience"
    assert body["model_version"] == "model_gateway:role_parsing"
