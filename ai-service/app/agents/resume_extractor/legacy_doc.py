"""Normalize legacy Word .doc into formats Docling / fallbacks can open."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

_log = logging.getLogger(__name__)

# OLE Compound File magic (true legacy .doc) vs ZIP (often mislabeled .docx)
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_ZIP_MAGIC = b"PK\x03\x04"


class LegacyDocError(RuntimeError):
    """Raised when a legacy .doc cannot be converted."""


def sniff_office_kind(path: Path) -> str:
    """Return 'docx' | 'ole-doc' | 'unknown' from file magic."""
    try:
        head = path.read_bytes()[:8]
    except OSError:
        return "unknown"
    if head.startswith(_ZIP_MAGIC):
        return "docx"
    if head.startswith(_OLE_MAGIC):
        return "ole-doc"
    return "unknown"


def _run(cmd: list[str], *, timeout: float = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _convert_with_textutil(src: Path, dest: Path, fmt: str) -> bool:
    textutil = shutil.which("textutil")
    if not textutil:
        return False
    result = _run(
        [
            textutil,
            "-convert",
            fmt,
            "-output",
            str(dest),
            str(src),
        ]
    )
    if result.returncode != 0 or not dest.exists() or dest.stat().st_size <= 0:
        _log.warning(
            "textutil %s failed for %s: %s",
            fmt,
            src.name,
            (result.stderr or result.stdout or "").strip()[:300],
        )
        return False
    return True


def _convert_with_libreoffice(src: Path, dest_dir: Path, fmt: str) -> Path | None:
    soffice = (
        shutil.which("soffice")
        or shutil.which("libreoffice")
        or "/Applications/LibreOffice.app/Contents/MacOS/soffice"
    )
    if not Path(soffice).exists():
        return None
    result = _run(
        [
            soffice,
            "--headless",
            "--nologo",
            "--nofirststartwizard",
            "--convert-to",
            fmt,
            "--outdir",
            str(dest_dir),
            str(src),
        ],
        timeout=120,
    )
    if result.returncode != 0:
        _log.warning(
            "LibreOffice convert failed for %s: %s",
            src.name,
            (result.stderr or result.stdout or "").strip()[:300],
        )
        return None
    expected = dest_dir / f"{src.stem}.{fmt}"
    if expected.exists() and expected.stat().st_size > 0:
        return expected
    # LibreOffice may sanitize the stem; pick newest matching suffix.
    matches = sorted(dest_dir.glob(f"*.{fmt}"), key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def prepare_doc_for_parse(path: Path, work_dir: Path) -> Path:
    """Return a path Docling can open (docx preferred, else txt).

    - Misnamed DOCX (ZIP magic + .doc extension) → copy as .docx
    - Legacy OLE .doc → convert via textutil/LibreOffice to .docx, else .txt
    """
    kind = sniff_office_kind(path)
    work_dir.mkdir(parents=True, exist_ok=True)

    if kind == "docx":
        dest = work_dir / f"{path.stem}.docx"
        shutil.copy2(path, dest)
        return dest

    # Prefer DOCX so Docling MsWord backend works.
    docx_dest = work_dir / f"{path.stem}.docx"
    if _convert_with_textutil(path, docx_dest, "docx"):
        return docx_dest

    lo_docx = _convert_with_libreoffice(path, work_dir, "docx")
    if lo_docx is not None:
        return lo_docx

    # Plain text last resort (still better than failing the pipeline).
    txt_dest = work_dir / f"{path.stem}.txt"
    if _convert_with_textutil(path, txt_dest, "txt"):
        return txt_dest

    lo_txt = _convert_with_libreoffice(path, work_dir, "txt")
    if lo_txt is not None:
        return lo_txt

    raise LegacyDocError(
        "Cannot open legacy .doc. Install macOS textutil (built-in) or LibreOffice "
        "(`soffice` on PATH), or re-save the resume as .docx / .pdf."
    )


def extract_text_from_legacy_doc(path: Path) -> str:
    """Extract plain text from a legacy .doc for OCR-fallback path."""
    with tempfile.TemporaryDirectory(prefix="legacy_doc_") as tmp:
        work = Path(tmp)
        # Prefer direct text conversion for fallback speed.
        txt_dest = work / f"{path.stem}.txt"
        if _convert_with_textutil(path, txt_dest, "txt"):
            return txt_dest.read_text(encoding="utf-8", errors="replace").strip()
        lo_txt = _convert_with_libreoffice(path, work, "txt")
        if lo_txt is not None:
            return lo_txt.read_text(encoding="utf-8", errors="replace").strip()

        prepared = prepare_doc_for_parse(path, work / "norm")
        if prepared.suffix.lower() == ".txt":
            return prepared.read_text(encoding="utf-8", errors="replace").strip()
        if prepared.suffix.lower() == ".docx":
            try:
                from docx import Document
            except ImportError as exc:
                raise LegacyDocError("python-docx is required to read converted DOCX") from exc
            document = Document(str(prepared))
            parts = [p.text.strip() for p in document.paragraphs if (p.text or "").strip()]
            return "\n\n".join(parts).strip()
        return prepared.read_text(encoding="utf-8", errors="replace").strip()
