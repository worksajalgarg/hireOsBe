"""
Dev-only persistence for model_gateway's per-turn metrics (see gateway.py's
_log_metrics) plus two sibling dev-tool files: the voice_agent's own
STT/TTS/EOU/VAD metrics (see voice_agent/dev_metrics.py) and a live
transcript snapshot. The voice_agent worker (a separate process from the
FastAPI app in main.py) is where all of this is actually generated during a
live interview; plain JSON files are the simplest way to get it from that
process to the dashboard served by main.py without adding an infra
dependency (Redis pub/sub etc.) for what is a local debugging tool, not a
product feature. Not intended for production observability — see
hireOsBe/CLAUDE.md's "full observability (OTel/Langfuse/Sentry-class
tracing, not yet implemented)" note for where that eventually belongs.
"""

import json
import os
import time
from pathlib import Path

_AI_SERVICE_ROOT = Path(__file__).resolve().parent.parent.parent
_DEV_DIR = _AI_SERVICE_ROOT / ".dev"


def is_dev_metrics_enabled() -> bool:
    """Gates every write in this module — moved here (from
    voice_agent/dev_metrics.py, which re-exports it for existing callers)
    since this is where the actual file-write decision belongs, and
    model_gateway must not depend on voice_agent. See append_metric()'s
    docstring for why this matters: it wasn't actually gating the LLM-call
    JSONL file before, unlike the STT/TTS/EOU/VAD one."""
    return os.environ.get("DEV_METRICS_ENABLED", "false").strip().lower() == "true"
METRICS_LOG_PATH = _DEV_DIR / "model_gateway_metrics.jsonl"
AGENT_METRICS_LOG_PATH = _DEV_DIR / "agent_metrics.jsonl"
TRANSCRIPT_SNAPSHOT_PATH = _DEV_DIR / "live_transcript.json"

# Keep append-only files bounded for long-running dev sessions without
# needing a background trim job — checked cheaply (byte size) on every write.
_MAX_BYTES_BEFORE_TRIM = 2_000_000
_KEEP_LINES_ON_TRIM = 1000


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": time.time(), **record}
    try:
        if path.exists() and path.stat().st_size > _MAX_BYTES_BEFORE_TRIM:
            lines = path.read_text().splitlines()[-_KEEP_LINES_ON_TRIM:]
            path.write_text("\n".join(lines) + "\n")
        with path.open("a") as f:
            f.write(json.dumps(record) + "\n")
    except OSError:
        # Best-effort: a dev dashboard write failure must never affect the
        # actual interview turn this metric describes.
        pass


def _read_recent_jsonl(path: Path, limit: int, after_ts: float | None = None) -> list[dict]:
    if not path.exists():
        return []
    # Bounded by the same _KEEP_LINES_ON_TRIM ceiling the file itself is
    # trimmed to — reading "recent" here never means scanning unbounded
    # history, so a plain tail-scan (no index/DB) stays cheap regardless of
    # how long an interview runs.
    lines = path.read_text().splitlines()[-_KEEP_LINES_ON_TRIM:]
    records = []
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if after_ts is not None and record.get("ts", 0) <= after_ts:
            continue
        records.append(record)
    return records[-limit:]


def _find_by_ts(path: Path, ts: float) -> dict | None:
    for record in _read_recent_jsonl(path, limit=_KEEP_LINES_ON_TRIM):
        if record.get("ts") == ts:
            return record
    return None


def _latest_ts(path: Path) -> float:
    """Cursor starting point for the WS watcher (dev_tools/metrics_ws.py) —
    treats everything already on disk as "history" the client fetches once
    via the existing REST endpoints, so live push only ever carries genuinely
    new records."""
    records = _read_recent_jsonl(path, limit=1)
    return records[-1]["ts"] if records else 0.0


def reset_dev_metrics() -> None:
    """Clears all three dev-dashboard files — called once per dispatched
    call/session (see worker.py's entrypoint) so the dashboard always shows
    only the *current* interview instead of an ever-growing mix of every
    session ever run on this machine. Best-effort: a failure here must never
    block a real interview from starting."""
    for path in (METRICS_LOG_PATH, AGENT_METRICS_LOG_PATH, TRANSCRIPT_SNAPSHOT_PATH):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def append_metric(record: dict) -> None:
    """Writes to the dev-only LLM-metrics JSONL file — gated on
    DEV_METRICS_ENABLED (previously this call was unconditional, unlike
    append_agent_metric() below, which meant this file grew unbounded in
    any environment, not just dev; see is_dev_metrics_enabled()'s
    docstring). gateway.py's metrics_logger.info(...) call is the separate,
    still-unconditional, production-safe aggregate-fields channel — this
    file write is purely the local dev-dashboard artifact."""
    if not is_dev_metrics_enabled():
        return
    _append_jsonl(METRICS_LOG_PATH, record)


def read_recent(limit: int = 200, after_ts: float | None = None) -> list[dict]:
    return _read_recent_jsonl(METRICS_LOG_PATH, limit, after_ts=after_ts)


def find_metric_by_ts(ts: float) -> dict | None:
    """Backs the dashboard's on-demand context-detail fetch (click a row to
    expand) — the list response omits the heavy fields, this looks up one
    specific record's full contents by its (effectively unique) timestamp."""
    return _find_by_ts(METRICS_LOG_PATH, ts)


def append_agent_metric(record: dict) -> None:
    """STT/TTS/EOU/VAD events from livekit-agents' own metrics_collected
    event — see voice_agent/dev_metrics.py. Kept in a separate file from the
    LLM-call metrics above since they come from a different source
    (framework-emitted, not model_gateway) and describe a different part of
    the pipeline."""
    _append_jsonl(AGENT_METRICS_LOG_PATH, record)


def read_recent_agent_metrics(limit: int = 200, after_ts: float | None = None) -> list[dict]:
    return _read_recent_jsonl(AGENT_METRICS_LOG_PATH, limit, after_ts=after_ts)


def latest_metric_ts() -> float:
    return _latest_ts(METRICS_LOG_PATH)


def latest_agent_metric_ts() -> float:
    return _latest_ts(AGENT_METRICS_LOG_PATH)


def slim_llm_record(record: dict) -> dict:
    """Drops the heavy context_detail fields (full window text + summary)
    down to a has_detail flag — used by both the REST list endpoint and the
    WS watcher (dev_tools/metrics_dashboard.py, dev_tools/metrics_ws.py) so
    neither ever ships the full text for rows nobody has clicked on yet."""
    slimmed = {k: v for k, v in record.items() if k != "context_detail"}
    slimmed["has_detail"] = bool(record.get("context_detail"))
    return slimmed


def write_transcript_snapshot(session_label: str, lines: list[str]) -> None:
    """Overwritten (not appended) each turn — this is a live snapshot of the
    current conversation, not a historical log. See voice_agent/gateway_llm.py."""
    TRANSCRIPT_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"session": session_label, "lines": lines, "updated_at": time.time()}
    try:
        TRANSCRIPT_SNAPSHOT_PATH.write_text(json.dumps(payload))
    except OSError:
        pass


def read_transcript_snapshot() -> dict | None:
    if not TRANSCRIPT_SNAPSHOT_PATH.exists():
        return None
    try:
        return json.loads(TRANSCRIPT_SNAPSHOT_PATH.read_text())
    except json.JSONDecodeError:
        return None
