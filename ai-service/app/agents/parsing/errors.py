class UnsupportedFileTypeError(Exception):
    """Raised for any extension other than .pdf/.docx — no .doc, no image/OCR
    formats, no .txt-passthrough magic. Narrow and predictable beats silently
    accepting something the extraction pipeline was never designed for."""


class ParsingError(Exception):
    """Raised for empty, corrupt, or otherwise unparseable input of an
    otherwise-supported file type."""
