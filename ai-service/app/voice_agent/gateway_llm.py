"""A livekit-agents LLM plugin that routes every conversational turn through
`model_gateway.run_stream()` instead of calling a provider SDK directly. This
file lives under app/, so it is scanned by
ai-service/tests/test_model_gateway_boundary.py exactly like every other
agent module — it must not (and does not) import openai/anthropic/etc.
itself.

Streams token-by-token through the gateway (still use_case_policy-gated) so
the TTS pipeline can start speaking the first sentence while the rest of the
answer is still generating, instead of waiting for the full completion.
"""

from __future__ import annotations

import uuid

from livekit.agents import llm
from livekit.agents.types import (
    DEFAULT_API_CONNECT_OPTIONS,
    NOT_GIVEN,
    APIConnectOptions,
    NotGivenOr,
)

from ..model_gateway.gateway import model_gateway

USE_CASE = "voice_interview_turn"


class GatewayLLM(llm.LLM):
    """Wraps the AI service's model gateway as a livekit-agents LLM."""

    def __init__(self, *, system_prompt: str) -> None:
        super().__init__()
        self._system_prompt = system_prompt

    @property
    def model(self) -> str:
        return USE_CASE

    @property
    def provider(self) -> str:
        return "hireos-model-gateway"

    def chat(
        self,
        *,
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool] | None = None,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
        parallel_tool_calls: NotGivenOr[bool] = NOT_GIVEN,
        tool_choice: NotGivenOr[llm.ToolChoice] = NOT_GIVEN,
        extra_kwargs: NotGivenOr[dict] = NOT_GIVEN,
    ) -> llm.LLMStream:
        return GatewayLLMStream(
            self,
            chat_ctx=chat_ctx,
            tools=tools or [],
            conn_options=conn_options,
            system_prompt=self._system_prompt,
        )


class GatewayLLMStream(llm.LLMStream):
    def __init__(
        self,
        llm_: GatewayLLM,
        *,
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool],
        conn_options: APIConnectOptions,
        system_prompt: str,
    ) -> None:
        super().__init__(llm_, chat_ctx=chat_ctx, tools=tools, conn_options=conn_options)
        self._system_prompt = system_prompt

    async def _run(self) -> None:
        transcript = _render_transcript(self._chat_ctx)
        # One id per turn, shared across all streamed chunks — matches the
        # framework's convention (its metrics/tracing groups chunks by id as
        # a single provider request, not one request per chunk).
        request_id = str(uuid.uuid4())
        async for piece in model_gateway.run_stream(
            use_case=USE_CASE,
            system_prompt=self._system_prompt,
            user_prompt=transcript,
        ):
            self._event_ch.send_nowait(
                llm.ChatChunk(
                    id=request_id,
                    delta=llm.ChoiceDelta(role="assistant", content=piece),
                )
            )


def _render_transcript(chat_ctx: llm.ChatContext) -> str:
    """The gateway takes a single (system_prompt, user_prompt) pair, not a
    message list, so the running conversation is flattened into a transcript
    the model can read as context for the next turn."""
    lines: list[str] = []
    for message in chat_ctx.messages():
        if message.role not in ("user", "assistant"):
            continue
        text = message.text_content
        if not text:
            continue
        speaker = "Candidate" if message.role == "user" else "Interviewer"
        lines.append(f"{speaker}: {text}")
    return "\n".join(lines)
