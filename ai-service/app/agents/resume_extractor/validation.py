"""Upload file validation (type, extension, size)."""

from __future__ import annotations

from dataclasses import dataclass
from zipfile import BadZipFile, ZipFile

from app.config import get_settings

from .formats import ALLOWED_CONTENT_TYPES, ALLOWED_EXTENSIONS


class FileValidationError(ValueError):
    """Raised when an uploaded resume fails validation."""


@dataclass(frozen=True)
class ValidatedUpload:
    filename: str
    content_type: str
    size_bytes: int
    extension: str


def _extension(filename: str) -> str:
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    if "." not in name:
        return ""
    return "." + name.rsplit(".", 1)[-1].lower()


def _safe_filename(filename: str) -> str:
    name = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    name = "".join(ch for ch in name if ch.isprintable() and ch not in "/\\\0")
    if name in ("", ".", ".."):
        raise FileValidationError("Filename is invalid")
    return name[:240]


def validate_file_signature(*, extension: str, file_bytes: bytes) -> None:
    """Reject obvious extension/content mismatches before invoking native parsers."""
    head = file_bytes[:16]
    if extension == ".pdf" and not head.startswith(b"%PDF-"):
        raise FileValidationError("File content is not a valid PDF")
    if extension == ".doc" and not head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        # Some browsers/users label a DOCX as .doc; the legacy converter supports it.
        if not head.startswith(b"PK\x03\x04"):
            raise FileValidationError("File content is not a valid DOC/DOCX document")
    if extension in {".docx", ".odt"}:
        try:
            from io import BytesIO

            with ZipFile(BytesIO(file_bytes)) as archive:
                names = set(archive.namelist())
        except (BadZipFile, OSError) as exc:
            raise FileValidationError(f"File content is not a valid {extension} archive") from exc
        if extension == ".docx" and "word/document.xml" not in names:
            raise FileValidationError("DOCX archive is missing word/document.xml")
        if extension == ".odt" and "content.xml" not in names:
            raise FileValidationError("ODT archive is missing content.xml")
    image_magic = {
        ".png": (b"\x89PNG\r\n\x1a\n",),
        ".jpg": (b"\xff\xd8\xff",),
        ".jpeg": (b"\xff\xd8\xff",),
        ".webp": (b"RIFF",),
        ".tif": (b"II*\x00", b"MM\x00*"),
        ".tiff": (b"II*\x00", b"MM\x00*"),
        ".bmp": (b"BM",),
    }
    if extension in image_magic and not any(head.startswith(m) for m in image_magic[extension]):
        raise FileValidationError(f"File content does not match {extension}")
    if extension in {".md", ".markdown", ".adoc", ".asciidoc", ".html", ".htm"}:
        if b"\x00" in file_bytes[:4096]:
            raise FileValidationError("Text document contains binary data")


def validate_upload(
    *,
    filename: str | None,
    content_type: str | None,
    size_bytes: int,
) -> ValidatedUpload:
    settings = get_settings()
    max_bytes = settings.resume_max_upload_mb * 1024 * 1024

    if not filename or not filename.strip():
        raise FileValidationError("Filename is required")

    safe_filename = _safe_filename(filename)
    ext = _extension(safe_filename)
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise FileValidationError(
            f"Unsupported file type '{ext or '(none)'}'. Allowed: {allowed}"
        )

    if size_bytes <= 0:
        raise FileValidationError("File is empty")

    if size_bytes > max_bytes:
        raise FileValidationError(
            f"File exceeds maximum size of {settings.resume_max_upload_mb}MB "
            f"({size_bytes} bytes)"
        )

    ctype = (content_type or "application/octet-stream").split(";")[0].strip().lower()
    if ctype not in ALLOWED_CONTENT_TYPES and ctype != "":
        raise FileValidationError(f"Unsupported content type '{ctype}'")

    return ValidatedUpload(
        filename=safe_filename,
        content_type=ctype or "application/octet-stream",
        size_bytes=size_bytes,
        extension=ext,
    )
