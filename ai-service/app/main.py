import logging
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

from .agents import (
    evaluation_engine,
    interview_orchestrator,
    matching_engine,
    resume_intelligence,
    role_intelligence,
)
from .dev_tools import metrics_dashboard
from .model_gateway.routing_config import load_routing_config
from .model_gateway.use_case_policy import USE_CASE_POLICIES

# Loaded first, before anything below reads os.environ (including
# _dev_metrics_dashboard_allowed() a few lines down, evaluated at import
# time). Does NOT rely on the IDE/debugger's own envFile support — that
# turned out to be unreliable for this launch config (a debugpy+
# module-launch quirk: APP_ENV came through as unset even with envFile set
# in launch.json, while cwd/python's ${workspaceFolder} substitution in the
# same config worked fine), so the app loads its own .env directly instead.
# override=False (the default) means real deployment env vars always win
# over this file, matching the semantics envFile is supposed to have.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Non-production environment names that may mount the /dev/metrics router
# below. Fail CLOSED: APP_ENV unset, empty, or anything not in this set
# (e.g. "staging", "production", a typo) means the router does NOT mount —
# see the comment at app.include_router(metrics_dashboard.router) for why
# this matters (it's an unauthenticated endpoint serving raw candidate
# transcript/PII when DEV_METRICS_ENABLED is also on).
_DEV_ENV_NAMES = {"local", "development", "dev"}


def _dev_metrics_dashboard_allowed() -> bool:
    return os.environ.get("APP_ENV", "").strip().lower() in _DEV_ENV_NAMES


def _configure_logging() -> None:
    """Structured JSON-to-stdout logging in non-dev environments — the
    FastAPI-process counterpart to what voice_agent/worker.py already gets
    for free from livekit-agents' own cli.run_app(...)/setup_logging()
    (confirmed from the installed package's source: `worker start` attaches
    a JsonFormatter to the root logger, so every logger in that process —
    including model_gateway.metrics — already emits structured JSON with no
    code change needed there). This process doesn't go through that CLI, so
    without this it would fall back to whatever uvicorn's own default
    format is. Reuses livekit-agents' JsonFormatter directly (already an
    installed dependency) rather than writing a second one.

    Deliberately does NOT ship logs anywhere — stdout capture/aggregation
    (CloudWatch/Datadog/Loki/etc.) is the deploying container/orchestrator's
    job, not application code's (12-factor logging convention); CLAUDE.md
    already tracks full OTel/Langfuse/Sentry-class observability as
    separate, bigger future work. This only makes sure what's emitted here
    is structured and complete, matching the worker process.

    In dev environments, leaves Python's default logging config alone
    (readable during local iteration) — matches
    _dev_metrics_dashboard_allowed()'s same APP_ENV gate above.

    Idempotent: guards against adding a second handler if this module is
    ever imported more than once in the same process (observed in this
    module's own test suite, which reloads app.main repeatedly — without
    this guard, each reload stacked another handler, duplicating every log
    line)."""
    if _dev_metrics_dashboard_allowed():
        return
    from livekit.agents.cli.log import JsonFormatter

    root = logging.getLogger()
    if any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(logging.INFO)


_configure_logging()


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Populates USE_CASE_POLICIES from config/model_routing.yaml before any
    # route can call get_policy() — see model_gateway/routing_config.py and
    # docs/adr/0005-config-driven-model-routing.md. voice_agent/worker.py
    # does the equivalent load for the separate worker process.
    path = Path(__file__).resolve().parent.parent / "config" / "model_routing.yaml"
    USE_CASE_POLICIES.update(load_routing_config(path))
    yield


app = FastAPI(title="Enterprise AI Hiring Platform — AI Service", lifespan=_lifespan)

app.include_router(role_intelligence.router)
app.include_router(resume_intelligence.router)
app.include_router(matching_engine.router)
app.include_router(interview_orchestrator.router)
app.include_router(evaluation_engine.router)
# Dev-only live view of model_gateway latency/context metrics — see
# dev_tools/metrics_dashboard.py's module docstring. No auth, no tenant
# scoping — when DEV_METRICS_ENABLED is also on, it serves raw candidate
# transcript/PII with zero access control. Only mounted when APP_ENV
# identifies a non-production environment (see _dev_metrics_dashboard_allowed
# above); fails closed (not mounted) if APP_ENV is unset or unrecognized, so
# forgetting to set it in a real deployment can't accidentally expose this.
if _dev_metrics_dashboard_allowed():
    app.include_router(metrics_dashboard.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
