from fastapi import FastAPI

from .agents import (
    evaluation_engine,
    interview_orchestrator,
    matching_engine,
    resume_intelligence,
    role_intelligence,
)

app = FastAPI(title="Enterprise AI Hiring Platform — AI Service")

app.include_router(role_intelligence.router)
app.include_router(resume_intelligence.router)
app.include_router(matching_engine.router)
app.include_router(interview_orchestrator.router)
app.include_router(evaluation_engine.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
