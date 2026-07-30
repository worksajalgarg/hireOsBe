"""Upload file validation (type, extension, size)."""

from __future__ import annotations

from dataclasses import dataclass

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
    name = filename.rsplit("/", 1)[-1]
    if "." not in name:
        return ""
    return "." + name.rsplit(".", 1)[-1].lower()


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

    ext = _extension(filename)
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
        # Extension already checked; warn-soft for odd MIME but still accept known extensions
        if ext not in ALLOWED_EXTENSIONS:
            raise FileValidationError(f"Unsupported content type '{ctype}'")

    return ValidatedUpload(
        filename=filename.strip(),
        content_type=ctype or "application/octet-stream",
        size_bytes=size_bytes,
        extension=ext,
    )
