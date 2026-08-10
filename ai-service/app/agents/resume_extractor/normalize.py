"""Text normalization before LLM extraction."""

from __future__ import annotations

import re
import unicodedata

DEFAULT_MAX_CHARS = 60_000


def normalize_text(text: str, *, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    if not text:
        return ""

    # NFKC for compatibility forms; strip control chars except newlines/tabs
    normalized = unicodedata.normalize("NFKC", text)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = "".join(
        ch for ch in normalized if ch in ("\n", "\t") or (unicodedata.category(ch)[0] != "C")
    )
    # Collapse runs of blank lines and horizontal whitespace
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    normalized = "\n".join(line.strip() for line in normalized.split("\n"))
    normalized = normalized.strip()

    if len(normalized) > max_chars:
        normalized = normalized[:max_chars].rstrip() + "\n\n[truncated]"

    return normalized
