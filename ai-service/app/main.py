from fastapi import FastAPI

from .agents import (
    evaluation_engine,
    interview_orchestrator,
    matching_engine,
    resume_intelligence,
    role_intelligence,
)
from .dev_tools import metrics_dashboard

app = FastAPI(title="Enterprise AI Hiring Platform — AI Service")

app.include_router(role_intelligence.router)
app.include_router(resume_intelligence.router)
app.include_router(matching_engine.router)
app.include_router(interview_orchestrator.router)
app.include_router(evaluation_engine.router)
# Dev-only live view of model_gateway latency/context metrics — see
# dev_tools/metrics_dashboard.py's module docstring. Not gated behind an env
# flag since main.py itself is only ever run locally/in dev today; revisit
# if this service is ever deployed with public network access.
app.include_router(metrics_dashboard.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
