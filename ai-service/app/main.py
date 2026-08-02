import os
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
