"""Shared resume upload extensions / MIME types (Docling-supported)."""

from __future__ import annotations

# Practical Docling formats for resumes (not every Docling InputFormat).
ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {
        # Documents
        ".pdf",
        ".docx",
        ".doc",
        ".odt",
        ".html",
        ".htm",
        ".md",
        ".markdown",
        ".adoc",
        ".asciidoc",
        # Scanned / image resumes
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".tif",
        ".tiff",
        ".bmp",
    }
)

ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset(
    {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.oasis.opendocument.text",
        "text/html",
        "application/xhtml+xml",
        "text/markdown",
        "text/x-markdown",
        "text/plain",  # some browsers send this for .md / .adoc
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/tiff",
        "image/bmp",
        "application/octet-stream",  # browsers sometimes send this
    }
)

ACCEPT_LABEL = "PDF, DOC, DOCX, ODT, HTML, Markdown, or image"
