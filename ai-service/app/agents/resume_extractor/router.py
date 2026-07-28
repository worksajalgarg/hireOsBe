"""FastAPI routes for resume extraction with SSE progress."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import StreamingResponse

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
async def extract_resume(file: UploadFile = File(...)) -> StreamingResponse:
    file_bytes = await file.read()
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
