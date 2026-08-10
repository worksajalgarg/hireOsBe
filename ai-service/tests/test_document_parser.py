import pytest

from app.agents.parsing.document_parser import parse_document, pdf_engine
from app.agents.parsing.errors import ParsingError, UnsupportedFileTypeError


def test_parses_valid_docx(synthetic_docx_bytes: bytes) -> None:
    result = parse_document(synthetic_docx_bytes, "resume.docx", None)
    assert result.char_count > 0
    assert "Placeholder Engineer" in result.text
    assert result.source_filename == "resume.docx"


def test_parses_valid_pdf_via_default_engine(synthetic_pdf_bytes: bytes) -> None:
    """Default engine is docling as of this session — see pdf_engine()."""
    result = parse_document(synthetic_pdf_bytes, "resume.pdf", None)
    assert result.char_count > 0
    assert "Placeholder Engineer" in result.text
    assert result.source_filename == "resume.pdf"


def test_parses_valid_pdf_via_pypdfium2_engine(monkeypatch, synthetic_pdf_bytes: bytes) -> None:
    monkeypatch.setenv("PDF_PARSER_ENGINE", "pypdfium2")
    result = parse_document(synthetic_pdf_bytes, "resume.pdf", None)
    assert result.char_count > 0
    assert "Placeholder Engineer" in result.text
    assert result.source_filename == "resume.pdf"


def test_empty_bytes_raises_parsing_error() -> None:
    with pytest.raises(ParsingError, match="empty file"):
        parse_document(b"", "resume.pdf", None)


def test_unsupported_extension_raises() -> None:
    """.zip, not .png — .png became a supported image extension this
    session (see _IMAGE_EXTENSIONS in document_parser.py), so it no longer
    demonstrates the "truly unsupported" case this test is for."""
    with pytest.raises(UnsupportedFileTypeError, match="unsupported file type"):
        parse_document(b"hello world", "resume.zip", None)


def test_unsupported_extension_doc_raises() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        parse_document(b"legacy binary word doc", "resume.doc", None)


def test_parses_valid_txt() -> None:
    result = parse_document(b"Plain text job description body.", "jd.txt", None)
    assert result.char_count > 0
    assert "Plain text job description" in result.text


def test_garbled_pdf_bytes_raise_parsing_error_not_crash() -> None:
    """Default engine (docling) — matches test_garbled_pdf_bytes... below
    which covers the same case explicitly for pypdfium2."""
    with pytest.raises(ParsingError, match="could not parse pdf"):
        parse_document(b"this is not a real pdf file at all", "resume.pdf", None)


def test_garbled_pdf_bytes_raise_parsing_error_via_pypdfium2_engine(monkeypatch) -> None:
    monkeypatch.setenv("PDF_PARSER_ENGINE", "pypdfium2")
    with pytest.raises(ParsingError, match="could not parse pdf"):
        parse_document(b"this is not a real pdf file at all", "resume.pdf", None)


def test_garbled_docx_bytes_raise_parsing_error_not_crash() -> None:
    with pytest.raises(ParsingError, match="could not parse docx"):
        parse_document(b"PK\x03\x04 not actually a valid zip/docx", "resume.docx", None)


def test_no_extension_raises_unsupported() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        parse_document(b"hello", "resume", None)


def test_pdf_engine_defaults_to_docling(monkeypatch) -> None:
    monkeypatch.delenv("PDF_PARSER_ENGINE", raising=False)
    assert pdf_engine() == "docling"


def test_pdf_engine_respects_pypdfium2_opt_out(monkeypatch) -> None:
    monkeypatch.setenv("PDF_PARSER_ENGINE", "pypdfium2")
    assert pdf_engine() == "pypdfium2"


def test_pdf_engine_respects_explicit_docling_env_var(monkeypatch) -> None:
    monkeypatch.setenv("PDF_PARSER_ENGINE", "docling")
    assert pdf_engine() == "docling"


def test_pdf_engine_falls_back_to_docling_on_unrecognized_value(monkeypatch) -> None:
    """Only an exact "pypdfium2" opts out — anything else, including a
    typo, collapses to the new default rather than raising."""
    monkeypatch.setenv("PDF_PARSER_ENGINE", "some-typo")
    assert pdf_engine() == "docling"


def test_parses_valid_pdf_via_docling_engine(monkeypatch, synthetic_pdf_bytes: bytes) -> None:
    monkeypatch.setenv("PDF_PARSER_ENGINE", "docling")
    result = parse_document(synthetic_pdf_bytes, "resume.pdf", None)
    assert result.char_count > 0
    assert "Placeholder Engineer" in result.text
    assert result.source_filename == "resume.pdf"
    assert result.page_count == 1
    assert result.used_ocr is False  # real text layer — OCR shouldn't fire


def test_parses_scanned_pdf_via_docling_engine_uses_ocr(
    monkeypatch, synthetic_scanned_pdf_bytes: bytes
) -> None:
    monkeypatch.setenv("PDF_PARSER_ENGINE", "docling")
    result = parse_document(synthetic_scanned_pdf_bytes, "scan.pdf", None)
    assert "Scanned Placeholder Text" in result.text
    assert result.used_ocr is True


def test_garbled_pdf_bytes_raise_parsing_error_via_docling_engine(monkeypatch) -> None:
    monkeypatch.setenv("PDF_PARSER_ENGINE", "docling")
    with pytest.raises(ParsingError, match="could not parse pdf"):
        parse_document(b"this is not a real pdf file at all", "resume.pdf", None)


def test_parses_valid_html(synthetic_html_bytes: bytes) -> None:
    result = parse_document(synthetic_html_bytes, "resume.html", None)
    assert result.char_count > 0
    assert "Placeholder Engineer" in result.text
    assert result.source_filename == "resume.html"


def test_arbitrary_bytes_as_html_do_not_crash() -> None:
    """HTMLDocumentBackend is lenient by design (confirmed directly against
    docling 2.118.1: is_valid() returns True even on binary garbage, and it
    decodes non-UTF-8 bytes some other way rather than raising) — there's
    no realistic "corrupt HTML" ParsingError case the way there is for
    PDF/DOCX/ODT's strict binary containers. This just locks in that
    arbitrary bytes produce *some* ParsedDocument, not a crash."""
    result = parse_document(b"\xff\xfe\x00\x01 not valid utf-8 or utf-16", "resume.html", None)
    assert isinstance(result.text, str)


def test_parses_valid_markdown(synthetic_markdown_bytes: bytes) -> None:
    result = parse_document(synthetic_markdown_bytes, "resume.md", None)
    assert result.char_count > 0
    assert "Placeholder Engineer" in result.text
    assert result.source_filename == "resume.md"


def test_parses_valid_asciidoc(synthetic_asciidoc_bytes: bytes) -> None:
    result = parse_document(synthetic_asciidoc_bytes, "resume.adoc", None)
    assert result.char_count > 0
    assert "Placeholder Engineer" in result.text
    assert result.source_filename == "resume.adoc"


def test_parses_valid_odt(synthetic_odt_bytes: bytes) -> None:
    result = parse_document(synthetic_odt_bytes, "resume.odt", None)
    assert result.char_count > 0
    assert "Placeholder Engineer" in result.text
    assert result.source_filename == "resume.odt"


def test_garbled_odt_bytes_raise_parsing_error_not_crash() -> None:
    with pytest.raises(ParsingError, match="could not parse odt|invalid or corrupt odt"):
        parse_document(b"PK\x03\x04 not actually a valid zip/odt", "resume.odt", None)


def test_parses_valid_image(synthetic_image_bytes: bytes) -> None:
    result = parse_document(synthetic_image_bytes, "resume.png", None)
    assert result.char_count > 0
    assert "Scanned Placeholder Resume" in result.text
    assert result.source_filename == "resume.png"
    assert result.used_ocr is True  # images have no embedded text layer at all


def test_garbled_image_bytes_raise_parsing_error_not_crash() -> None:
    with pytest.raises(ParsingError, match="could not parse image"):
        parse_document(b"this is not a real image file at all", "resume.png", None)
