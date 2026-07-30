from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .ssl_certs import configure_huggingface_offline, configure_ssl_certs

# Must run before Docling / HuggingFace / urllib downloads.
configure_ssl_certs()
configure_huggingface_offline()

from .agents import (
    evaluation_engine,
    interview_orchestrator,
    matching_engine,
    resume_intelligence,
    role_intelligence,
)
from .agents.resume_extractor import router as resume_extractor_router
from .config import get_settings

# Reload settings after SSL/env bootstrap (clears any stale cache).
get_settings.cache_clear()
settings = get_settings()

app = FastAPI(title="Enterprise AI Hiring Platform — AI Service")

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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.on_event("startup")
async def _startup_clear_settings_cache() -> None:
    get_settings.cache_clear()
