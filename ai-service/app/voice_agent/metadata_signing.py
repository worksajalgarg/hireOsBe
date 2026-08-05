"""Verifies the HMAC signature platform's interviews.service.ts attaches to
room metadata (see room-metadata-signing.ts, worker.py's entrypoint()) —
see docs/adr/0006-interview-transcript-storage.md's Phase E section.

Must build the exact same canonical string as the TypeScript side — keep
the two in sync by hand; there's no shared package between the two
runtimes (see hireOsBe/CLAUDE.md's "Shared type contracts" note).
"""

import hashlib
import hmac

# U+0001 (SOH) — matches room-metadata-signing.ts's FIELD_SEPARATOR exactly.
_FIELD_SEPARATOR = "\x01"


def _canonical_string(
    *, tenant_id: str, session_id: str, session_type: str, resume_context: str | None
) -> str:
    return _FIELD_SEPARATOR.join(
        [tenant_id, session_id, session_type, resume_context or ""]
    )


def verify_metadata_signature(metadata: dict, secret: str) -> bool:
    """True only if `metadata["metadataSignature"]` matches an HMAC-SHA256
    over the other fields, computed with `secret`. False on any missing
    field, missing signature, or mismatch — never raises, so callers can
    treat "not verified" uniformly regardless of why."""
    signature = metadata.get("metadataSignature")
    tenant_id = metadata.get("tenantId")
    session_id = metadata.get("sessionId")
    session_type = metadata.get("sessionType")
    if not signature or not tenant_id or not session_id or not session_type:
        return False

    expected = hmac.new(
        secret.encode(),
        _canonical_string(
            tenant_id=tenant_id,
            session_id=session_id,
            session_type=session_type,
            resume_context=metadata.get("resumeContext"),
        ).encode(),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)
