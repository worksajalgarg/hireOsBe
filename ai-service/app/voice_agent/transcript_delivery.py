"""Delivers a completed interview's transcript + evaluation to platform's
POST /internal/interview-sessions/:id/transcript — see worker.py's shutdown
callback and docs/adr/0006-interview-transcript-storage.md.

This is an outbound, post-call, best-effort push: it runs after the
interview has already finished, so a platform outage delays *persistence*,
never the interview itself. Delivery reliability comes from a small local
outbox (data/pending_transcripts/), not a message queue — the payload is
written to disk before the POST attempt and only deleted on a confirmed
2xx, so a transient network blip or a platform restart doesn't lose data.
flush_pending() retries anything still sitting there at the next worker
startup.
"""

import json
import logging
from pathlib import Path

import httpx

logger = logging.getLogger("voice_agent")

_AI_SERVICE_ROOT = Path(__file__).resolve().parent.parent.parent
OUTBOX_DIR = _AI_SERVICE_ROOT / "data" / "pending_transcripts"

_POST_TIMEOUT_S = 15.0


def _outbox_path(session_id: str) -> Path:
    return OUTBOX_DIR / f"{session_id}.json"


def write_to_outbox(session_id: str, payload: dict) -> Path:
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    path = _outbox_path(session_id)
    path.write_text(json.dumps(payload))
    return path


async def _post(
    session_id: str, payload: dict, *, base_url: str, secret: str
) -> bool:
    url = f"{base_url.rstrip('/')}/internal/interview-sessions/{session_id}/transcript"
    headers = {"Authorization": f"Bearer {secret}"}
    try:
        async with httpx.AsyncClient(timeout=_POST_TIMEOUT_S) as client:
            response = await client.post(url, json=payload, headers=headers)
    except httpx.HTTPError:
        logger.warning("transcript delivery for session %s raised", session_id, exc_info=True)
        return False

    if 200 <= response.status_code < 300:
        return True
    logger.warning(
        "transcript delivery for session %s failed: HTTP %d %s",
        session_id, response.status_code, response.text[:500],
    )
    return False


async def deliver_transcript(
    session_id: str, payload: dict, *, base_url: str, secret: str
) -> None:
    """Writes to the outbox first, then attempts delivery — the file is
    only removed on success, so a failed attempt leaves the payload for
    flush_pending() to retry on the next worker startup."""
    path = write_to_outbox(session_id, payload)
    delivered = await _post(session_id, payload, base_url=base_url, secret=secret)
    if delivered:
        path.unlink(missing_ok=True)
        logger.info("transcript delivered for session %s", session_id)
    else:
        logger.warning("transcript for session %s kept in outbox at %s for retry", session_id, path)


async def flush_pending(*, base_url: str, secret: str) -> None:
    """Called once at worker startup (see worker.py's main()) — retries any
    transcript a prior process wrote to the outbox but never successfully
    delivered (e.g. platform was down at the time)."""
    if not OUTBOX_DIR.exists():
        return
    for path in sorted(OUTBOX_DIR.glob("*.json")):
        session_id = path.stem
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            logger.warning("Could not read pending transcript %s, leaving it as-is", path)
            continue
        delivered = await _post(session_id, payload, base_url=base_url, secret=secret)
        if delivered:
            path.unlink(missing_ok=True)
            logger.info("Delivered previously-pending transcript for session %s", session_id)
