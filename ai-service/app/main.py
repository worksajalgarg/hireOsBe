import logging
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .ssl_certs import configure_huggingface_offline, configure_ssl_certs

# Loaded first, before anything below reads os.environ.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Must run before Docling / HuggingFace / urllib downloads.
configure_ssl_certs()
configure_huggingface_offline()

from .agents import (  # noqa: E402
    evaluation_engine,
    interview_orchestrator,
    matching_engine,
    resume_intelligence,
    role_intelligence,
)
from .agents.resume_extractor import router as resume_extractor_router  # noqa: E402
from .config import get_settings  # noqa: E402
from .dev_tools import metrics_dashboard  # noqa: E402
from .model_gateway.routing_config import load_routing_config  # noqa: E402
from .model_gateway.use_case_policy import USE_CASE_POLICIES  # noqa: E402

get_settings.cache_clear()
settings = get_settings()

_DEV_ENV_NAMES = {"local", "development", "dev"}


def _dev_metrics_dashboard_allowed() -> bool:
    return os.environ.get("APP_ENV", "").strip().lower() in _DEV_ENV_NAMES


def _configure_logging() -> None:
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
    get_settings.cache_clear()
    path = Path(__file__).resolve().parent.parent / "config" / "model_routing.yaml"
    USE_CASE_POLICIES.update(load_routing_config(path))
    yield


app = FastAPI(title="Enterprise AI Hiring Platform — AI Service", lifespan=_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(role_intelligence.router)
app.include_router(resume_intelligence.router)
app.include_router(resume_extractor_router)
app.include_router(matching_engine.router)
app.include_router(interview_orchestrator.router)
app.include_router(evaluation_engine.router)
if _dev_metrics_dashboard_allowed():
    app.include_router(metrics_dashboard.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
