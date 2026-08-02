"""Shared livekit-agents streaming plumbing used by both voice personas —
GatewayLLM (candidate interview, gateway_llm.py) and DiscoveryLLM (hiring
manager discovery, discovery_llm.py). Both stream a turn through
model_gateway.run_stream() and emit livekit ChatChunks the same way; only
how each builds its per-turn user_prompt and what happens after a turn
finishes streaming actually differ between the two personas. Extracted here
so that plumbing isn't copy-pasted into two classes that can silently drift
apart when one gets a bug fix and the other doesn't.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from livekit.agents import llm

from ..model_gateway.gateway import model_gateway


async def stream_turn_chunks(
    *,
    use_case: str,
    system_prompt: str,
    user_prompt: str,
    context_detail: dict | None = None,
) -> AsyncIterator[llm.ChatChunk]:
    """Streams one conversational turn through the model gateway, yielding
    one ChatChunk per piece under a single shared request_id (matching the
    framework's convention — its metrics/tracing groups chunks by id as one
    provider request, not one request per chunk). Callers accumulate the
    full reply by concatenating each chunk's delta.content as they iterate."""
    request_id = str(uuid.uuid4())
    async for piece in model_gateway.run_stream(
        use_case=use_case,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        context_detail=context_detail,
    ):
        yield llm.ChatChunk(id=request_id, delta=llm.ChoiceDelta(role="assistant", content=piece))


def extract_transcript_lines(
    chat_ctx: llm.ChatContext, *, user_label: str, assistant_label: str
) -> list[str]:
    """Full ordered "Speaker: text" lines for the conversation so far — not
    trimmed here, callers decide how much of it (plus whatever state they
    track) to actually send. Labels are parameterized since the two personas
    have different speakers (Candidate/Interviewer vs. Hiring Manager/Agent)."""
    lines: list[str] = []
    for message in chat_ctx.messages():
        if message.role not in ("user", "assistant"):
            continue
        text = message.text_content
        if not text:
            continue
        speaker = user_label if message.role == "user" else assistant_label
        lines.append(f"{speaker}: {text}")
    return lines


def extract_pending_instructions(
    chat_ctx: llm.ChatContext, system_prompt: str | None = None
) -> str | None:
    """Surfaces a one-off instruction the framework attached via
    AgentSession.generate_reply(instructions=...) — used for the opening
    greeting and silence nudges (see conversation_start.py). For a
    "stateless" LLM like ours, livekit-agents delivers this by injecting a
    system-role message into chat_ctx (generation.py's update_instructions),
    not as a parameter our chat()/LLMStream ever sees.

    If system_prompt is provided, any system message matching system_prompt
    is skipped so the 10,000+ char system prompt isn't duplicated into
    user_prompt on every turn."""
    for message in chat_ctx.messages():
        if message.role == "system" and message.text_content:
            if system_prompt and message.text_content.strip() == system_prompt.strip():
                continue
            return message.text_content
    return None
