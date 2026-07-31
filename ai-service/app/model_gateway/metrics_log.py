"""
Dev-only persistence for model_gateway's per-turn metrics (see gateway.py's
_log_metrics). The voice_agent worker (a separate process from the FastAPI
app in main.py) is where these metrics are actually generated during a live
interview; a JSON-lines file is the simplest way to get them from that
process to the dashboard served by main.py without adding an infra
dependency (Redis pub/sub etc.) for what is a local debugging tool, not a
product feature. Not intended for production observability — see
hireOsBe/CLAUDE.md's "full observability (OTel/Langfuse/Sentry-class
tracing, not yet implemented)" note for where that eventually belongs.
"""

import json
import time
from pathlib import Path

_AI_SERVICE_ROOT = Path(__file__).resolve().parent.parent.parent
METRICS_LOG_PATH = _AI_SERVICE_ROOT / ".dev" / "model_gateway_metrics.jsonl"

# Keep the file bounded for long-running dev sessions without needing a
# background trim job — checked cheaply (byte size) on every write.
_MAX_BYTES_BEFORE_TRIM = 2_000_000
_KEEP_LINES_ON_TRIM = 1000


def append_metric(record: dict) -> None:
    METRICS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": time.time(), **record}
    try:
        if METRICS_LOG_PATH.exists() and METRICS_LOG_PATH.stat().st_size > _MAX_BYTES_BEFORE_TRIM:
            lines = METRICS_LOG_PATH.read_text().splitlines()[-_KEEP_LINES_ON_TRIM:]
            METRICS_LOG_PATH.write_text("\n".join(lines) + "\n")
        with METRICS_LOG_PATH.open("a") as f:
            f.write(json.dumps(record) + "\n")
    except OSError:
        # Best-effort: a dev dashboard write failure must never affect the
        # actual interview turn this metric describes.
        pass


def read_recent(limit: int = 200) -> list[dict]:
    if not METRICS_LOG_PATH.exists():
        return []
    lines = METRICS_LOG_PATH.read_text().splitlines()[-limit:]
    records = []
    for line in lines:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records
