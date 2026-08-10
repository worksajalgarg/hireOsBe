import pytest

from app.agents.parsing.document_parser import parse_document
from app.agents.parsing.errors import ParsingError, UnsupportedFileTypeError


def test_parses_valid_docx(synthetic_docx_bytes: bytes) -> None:
    result = parse_document(synthetic_docx_bytes, "resume.docx", None)
    assert result.char_count > 0
    assert "Placeholder Engineer" in result.text
    assert result.source_filename == "resume.docx"


def test_parses_valid_pdf(synthetic_pdf_bytes: bytes) -> None:
    result = parse_document(synthetic_pdf_bytes, "resume.pdf", None)
    assert result.char_count > 0
    assert "Placeholder Engineer" in result.text
    assert result.source_filename == "resume.pdf"


def test_empty_bytes_raises_parsing_error() -> None:
    with pytest.raises(ParsingError, match="empty file"):
        parse_document(b"", "resume.pdf", None)


def test_unsupported_extension_raises() -> None:
    with pytest.raises(UnsupportedFileTypeError, match="unsupported file type"):
        parse_document(b"hello world", "resume.png", None)


def test_unsupported_extension_doc_raises() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        parse_document(b"legacy binary word doc", "resume.doc", None)


def test_parses_valid_txt() -> None:
    result = parse_document(b"Plain text job description body.", "jd.txt", None)
    assert result.char_count > 0
    assert "Plain text job description" in result.text


def test_garbled_pdf_bytes_raise_parsing_error_not_crash() -> None:
    with pytest.raises(ParsingError, match="could not parse pdf"):
        parse_document(b"this is not a real pdf file at all", "resume.pdf", None)


def test_garbled_docx_bytes_raise_parsing_error_not_crash() -> None:
    with pytest.raises(ParsingError, match="could not parse docx"):
        parse_document(b"PK\x03\x04 not actually a valid zip/docx", "resume.docx", None)


def test_no_extension_raises_unsupported() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        parse_document(b"hello", "resume", None)
