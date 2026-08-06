"""FastAPI routes for resume extraction with SSE progress."""

from __future__ import annotations

import json
import secrets
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, File, Header, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.config import get_settings

from .pipeline import run_extraction_pipeline
from .schemas import StageEvent

router = APIRouter(prefix="/resume-extractor", tags=["resume-extractor"])


def _sse_format(event: StageEvent) -> str:
    payload = event.model_dump(mode="json")
    return f"data: {json.dumps(payload)}\n\n"


@router.get("/health")
async def health() -> dict[str, str]:
    return {"agent": "resume-extractor", "status": "ok"}


@router.post("/extract")
async def extract_resume(
    file: UploadFile = File(...),
    internal_token: Annotated[str | None, Header(alias="x-ai-service-token")] = None,
) -> StreamingResponse:
    settings = get_settings()
    if settings.ai_service_token and not secrets.compare_digest(
        internal_token or "", settings.ai_service_token
    ):
        raise HTTPException(status_code=401, detail="Invalid AI service token")
    max_bytes = settings.resume_max_upload_mb * 1024 * 1024
    parts: list[bytes] = []
    size = 0
    while chunk := await file.read(1024 * 1024):
        size += len(chunk)
        if size > max_bytes:
            await file.close()
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds maximum size of {settings.resume_max_upload_mb}MB",
            )
        parts.append(chunk)
    file_bytes = b"".join(parts)
    await file.close()
    filename = file.filename or "upload.bin"
    content_type = file.content_type

    async def event_stream() -> AsyncIterator[str]:
        async for event in run_extraction_pipeline(
            filename=filename,
            content_type=content_type,
            file_bytes=file_bytes,
        ):
            yield _sse_format(event)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
