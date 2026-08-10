import io

from fastapi.testclient import TestClient

from app.agents.resume_intelligence import (
    _backfill_thin_unparsed_sections,
    _drop_unparsed_sections_captured_elsewhere,
    _has_substantial_content,
)
from app.agents.resume_intelligence_schema import (
    EvidencedClaim,
    ResumeExtractionLLMOutput,
    SkillClaim,
    UnparsedSection,
)
from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/resume-intelligence/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_empty_file_returns_422() -> None:
    response = client.post(
        "/resume-intelligence/parse", files={"file": ("resume.pdf", b"", "application/pdf")}
    )
    assert response.status_code == 422


def test_unsupported_file_type_returns_415() -> None:
    """.zip, not .png — .png became a supported image extension this
    session (see document_parser.py's _IMAGE_EXTENSIONS)."""
    response = client.post(
        "/resume-intelligence/parse", files={"file": ("resume.zip", b"hello", "application/zip")}
    )
    assert response.status_code == 415


def test_near_empty_text_pdf_returns_422_before_calling_gateway(monkeypatch) -> None:
    """A scanned/image-only PDF (or here, a synthetic near-blank one) must
    never reach the LLM — wasted cost and a misleading "resume has nothing"
    result rather than a clear "couldn't extract text" error."""
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
        "app.agents.resume_intelligence.model_gateway.run_structured", fake_run_structured
    )

    response = client.post(
        "/resume-intelligence/parse",
        files={"file": ("resume.pdf", near_empty_pdf, "application/pdf")},
    )
    assert response.status_code == 422
    assert called is False


def test_gateway_failure_returns_502(monkeypatch, synthetic_pdf_bytes: bytes) -> None:
    async def fake_run_structured(**kwargs):
        raise RuntimeError("provider chain exhausted")

    monkeypatch.setattr(
        "app.agents.resume_intelligence.model_gateway.run_structured", fake_run_structured
    )

    response = client.post(
        "/resume-intelligence/parse",
        files={"file": ("resume.pdf", synthetic_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 502


def test_empty_extraction_on_substantial_resume_returns_502(monkeypatch) -> None:
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for i in range(12):
        c.drawString(72, 750 - i * 20, f"Resume content line number {i} with real details.")
    c.save()
    long_pdf = buf.getvalue()

    async def fake_run_structured(**kwargs):
        return ResumeExtractionLLMOutput()  # everything empty, no unparsed_sections either

    monkeypatch.setattr(
        "app.agents.resume_intelligence.model_gateway.run_structured", fake_run_structured
    )

    response = client.post(
        "/resume-intelligence/parse", files={"file": ("resume.pdf", long_pdf, "application/pdf")}
    )
    assert response.status_code == 502


def test_happy_path_returns_structured_extraction(monkeypatch, synthetic_pdf_bytes: bytes) -> None:
    fake_output = ResumeExtractionLLMOutput(
        candidate_name="Test Candidate",
        professional_summary="Backend engineer focused on distributed systems.",
        skills=[SkillClaim(skill="Python", source_text="Placeholder Engineer")],
        certifications=[
            EvidencedClaim(claim="AWS Certified Solutions Architect", source_text="AWS Certified")
        ],
        projects=[
            EvidencedClaim(claim="Built a rate limiter", source_text="Built a rate limiter in Go")
        ],
        awards=[
            EvidencedClaim(claim="Employee of the Year 2024", source_text="Employee of the Year")
        ],
        publications=[
            EvidencedClaim(claim="Scaling Postgres at 10x", source_text="Scaling Postgres")
        ],
        languages=[EvidencedClaim(claim="English (fluent)", source_text="English (fluent)")],
        unparsed_sections=[UnparsedSection(section_title="Hobbies", raw_text="Chess, hiking")],
    )

    async def fake_run_structured(**kwargs):
        assert kwargs["use_case"] == "resume_parsing"
        return fake_output

    monkeypatch.setattr(
        "app.agents.resume_intelligence.model_gateway.run_structured", fake_run_structured
    )

    response = client.post(
        "/resume-intelligence/parse",
        files={"file": ("resume.pdf", synthetic_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["candidate_name"] == "Test Candidate"
    assert body["professional_summary"] == "Backend engineer focused on distributed systems."
    assert body["skills"][0]["skill"] == "Python"
    assert body["certifications"][0]["claim"] == "AWS Certified Solutions Architect"
    assert body["projects"][0]["claim"] == "Built a rate limiter"
    assert body["awards"][0]["claim"] == "Employee of the Year 2024"
    assert body["publications"][0]["claim"] == "Scaling Postgres at 10x"
    assert body["languages"][0]["claim"] == "English (fluent)"
    assert body["unparsed_sections"][0]["section_title"] == "Hobbies"
    assert body["unparsed_sections"][0]["raw_text"] == "Chess, hiking"
    # "Chess, hiking" (13 chars) isn't past the thinness margin over
    # "Hobbies" (7 chars) — genuinely thin by this heuristic, so the amber
    # "could not confidently parse" warning is earned here.
    assert body["unparsed_sections"][0]["has_content"] is False
    assert body["source_filename"] == "resume.pdf"
    assert body["model_version"] == "model_gateway:resume_parsing"


def test_substantial_unparsed_section_is_flagged_has_content(
    monkeypatch, synthetic_pdf_bytes: bytes
) -> None:
    """Reproduces the real case that motivated has_content: a resume's
    "Volunteering"/"Coursework"-shaped section with substantial, cleanly
    extracted text — not thin, not garbled — should not get the same
    "could not confidently parse" alarm as a genuinely thin stub."""
    fake_output = ResumeExtractionLLMOutput(
        candidate_name="Test Candidate",
        unparsed_sections=[
            UnparsedSection(
                section_title="Volunteering",
                raw_text=(
                    "CodeChef College Chapter (IIIT Sonepat) Executive Team Member, "
                    "Problem Setter and Tester in Coding Competitions"
                ),
            )
        ],
    )

    async def fake_run_structured(**kwargs):
        return fake_output

    monkeypatch.setattr(
        "app.agents.resume_intelligence.model_gateway.run_structured", fake_run_structured
    )

    response = client.post(
        "/resume-intelligence/parse",
        files={"file": ("resume.pdf", synthetic_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["unparsed_sections"][0]["section_title"] == "Volunteering"
    assert body["unparsed_sections"][0]["has_content"] is True


def test_backfill_recovers_real_text_when_model_echoes_the_heading() -> None:
    """Reproduces the real bug: the model returned {"section_title":
    "Courses", "raw_text": "Courses"} for a resume whose Courses section
    genuinely had content — confirmed by grepping a real extraction for
    that content and finding zero matches anywhere in the response."""
    source = (
        "EDUCATION\nB.Tech, Example University\nCourses\n"
        "Advanced Data Structures — Coursera, 2023\n"
        "Cloud Computing Fundamentals — edX, 2022\n\n"
        "WORK EXPERIENCE\nSoftware Engineer"
    )
    sections = [UnparsedSection(section_title="Courses", raw_text="Courses")]

    result = _backfill_thin_unparsed_sections(sections, source)

    assert len(result) == 1
    assert result[0].section_title == "Courses"
    assert "Advanced Data Structures" in result[0].raw_text
    assert "Cloud Computing Fundamentals" in result[0].raw_text
    assert "WORK EXPERIENCE" not in result[0].raw_text  # cut at the paragraph break


def test_backfill_leaves_substantive_raw_text_untouched() -> None:
    sections = [UnparsedSection(section_title="Hobbies", raw_text="Chess, hiking, painting")]

    result = _backfill_thin_unparsed_sections(sections, "Hobbies\nChess, hiking, painting")

    assert result[0].raw_text == "Chess, hiking, painting"


def test_backfill_leaves_section_as_is_when_title_not_found_in_source() -> None:
    sections = [UnparsedSection(section_title="Volunteering", raw_text="Volunteering")]

    result = _backfill_thin_unparsed_sections(sections, "Completely unrelated resume text.")

    assert result[0].raw_text == "Volunteering"  # no crash, no fabrication


def test_backfill_rejects_a_sibling_heading_as_recovered_content() -> None:
    """Reproduces the real docling artifact: two orphaned heading-only
    labels ("Courses", "Achievements") end up adjacent at the end of the
    extracted text, nowhere near the bullets they actually caption. A naive
    proximity search would recover "Achievements" as if it were Courses's
    real content — actively misleading, worse than the original echo."""
    source = "...end of resume content.\nCourses\nAchievements"
    sections = [
        UnparsedSection(section_title="Courses", raw_text="Courses"),
        UnparsedSection(section_title="Achievements", raw_text="Achievements"),
    ]

    result = _backfill_thin_unparsed_sections(sections, source)

    assert result[0].raw_text == "Courses"  # left as-is, not "Achievements"
    assert result[1].raw_text == "Achievements"  # left as-is, nothing follows it


def test_drop_unparsed_sections_captured_elsewhere_removes_duplicate_stub() -> None:
    """Reproduces the real duplication: a resume's Courses content is
    correctly captured under education (with section="Courses"), but the
    model *also* flagged an unparsed_sections stub for the same title."""
    output = ResumeExtractionLLMOutput(
        education=[
            EvidencedClaim(
                claim="Advanced Data Structures — Coursera, 2023",
                source_text="Advanced Data Structures — Coursera, 2023",
                section="Courses",
            )
        ],
        unparsed_sections=[
            UnparsedSection(section_title="Courses", raw_text="Advanced Data Structures")
        ],
    )

    result = _drop_unparsed_sections_captured_elsewhere(output.unparsed_sections, output)

    assert result == []


def test_drop_unparsed_sections_captured_elsewhere_keeps_genuinely_unmatched_sections() -> None:
    output = ResumeExtractionLLMOutput(
        education=[
            EvidencedClaim(
                claim="B.Tech, Example University",
                source_text="B.Tech, Example University",
                section="Education",
            )
        ],
        unparsed_sections=[UnparsedSection(section_title="Hobbies", raw_text="Chess, hiking")],
    )

    result = _drop_unparsed_sections_captured_elsewhere(output.unparsed_sections, output)

    assert len(result) == 1
    assert result[0].section_title == "Hobbies"


def test_has_substantial_content_true_for_the_volunteering_coursework_case() -> None:
    """The real case that motivated this: substantial, cleanly extracted
    text under a section type the schema doesn't model — should read as
    "has content," not as a thin/ambiguous stub."""
    section = UnparsedSection(
        section_title="Coursework",
        raw_text=(
            "- Data Structures and Algorithms (DSA)\n- Operating Systems (OS)\n"
            "- Object Oriented Programming (OOPS)\n- Database Management Systems (DBMS)"
        ),
    )
    assert _has_substantial_content(section) is True


def test_has_substantial_content_false_for_a_bare_heading_echo() -> None:
    """The original bug's exact shape: raw_text is just the heading
    repeated back, no real content at all."""
    section = UnparsedSection(section_title="Courses", raw_text="Courses")
    assert _has_substantial_content(section) is False


def test_has_substantial_content_false_for_empty_raw_text() -> None:
    section = UnparsedSection(section_title="Hobbies", raw_text="")
    assert _has_substantial_content(section) is False


def test_has_substantial_content_is_section_name_blind() -> None:
    """Never special-cases a section title — the same length-based
    predicate applies regardless of what an unmodeled section is called,
    which is the whole point (works for any resume, not just the two
    section names seen in practice so far)."""
    thin = UnparsedSection(section_title="Patents", raw_text="Patents")
    substantial = UnparsedSection(
        section_title="Patents", raw_text="US Patent 12345678: A novel method for widget assembly."
    )
    assert _has_substantial_content(thin) is False
    assert _has_substantial_content(substantial) is True
