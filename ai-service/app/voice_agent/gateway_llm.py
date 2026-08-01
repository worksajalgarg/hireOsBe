"""A livekit-agents LLM plugin that routes every conversational turn through
`model_gateway.run_stream()` instead of calling a provider SDK directly. This
file lives under app/, so it is scanned by
ai-service/tests/test_model_gateway_boundary.py exactly like every other
agent module — it must not (and does not) import openai/anthropic/etc.
itself.

Streams token-by-token through the gateway (still use_case_policy-gated) so
the TTS pipeline can start speaking the first sentence while the rest of the
answer is still generating, instead of waiting for the full completion.

Long-conversation memory: sending the full transcript every turn makes every
call bigger (and slower) for the rest of the interview. Sending only the
last N lines is fast but makes the agent forget anything earlier. This file
does both without trading one for the other: each turn sends a bounded
recent window plus a running summary of everything older (see
GatewayLLM._maybe_consolidate). The summary is updated in a background
asyncio task *after* a turn's response has already started streaming, using
the gap while the candidate is speaking their next answer — so consolidation
never adds latency to the turn a candidate is actually waiting on.
"""

from __future__ import annotations

import asyncio
import logging

from livekit.agents import llm
from livekit.agents.types import (
    DEFAULT_API_CONNECT_OPTIONS,
    NOT_GIVEN,
    APIConnectOptions,
    NotGivenOr,
)

from ..model_gateway.gateway import model_gateway
from ..model_gateway.metrics_log import write_transcript_snapshot
from .dev_metrics import is_dev_metrics_enabled
from .llm_streaming import (
    extract_pending_instructions,
    extract_transcript_lines,
    stream_turn_chunks,
)

logger = logging.getLogger("voice_agent")

USE_CASE = "voice_interview_turn"
SUMMARY_USE_CASE = "voice_interview_summary"

# Recent lines (roughly candidate+interviewer turns) sent verbatim every
# call. Consolidation kicks in once this many lines *beyond* the window have
# piled up — folding in a small batch at a time rather than on every single
# turn's overflow. Reduced from 16+8: summaries are lossy (they paraphrase,
# don't preserve exact wording), so a smaller verbatim window with a more
# frequent, fresher summary is the better trade at Groq's speed/cost.
WINDOW_LINES = 10
CONSOLIDATION_BUFFER_LINES = 6

_SUMMARY_INSTRUCTIONS = """You are maintaining a running summary of an ongoing job interview \
for the interviewer's own later reference — not for the candidate. Given the existing summary \
(if any) and a new chunk of the transcript, produce an updated summary that preserves: topics \
and questions already asked, key facts the candidate stated about their background, and any \
commitments made (e.g. "will follow up on X"). Keep it compact — a few sentences or short \
bullet points, not a full retelling. Never include a score, rating, or hire/reject judgment."""


class GatewayLLM(llm.LLM):
    """Wraps the AI service's model gateway as a livekit-agents LLM. One
    instance lives for the whole interview (see session.py), so the rolling
    summary below persists across turns — it must not be reset per-turn."""

    def __init__(self, *, system_prompt: str, session_label: str = "unknown") -> None:
        super().__init__()
        self._system_prompt = system_prompt
        # Identifies which interview these dev-dashboard metrics/transcript
        # entries belong to (currently just the LiveKit room name) — not
        # used for anything beyond dev tooling. See metrics_log.py.
        self._session_label = session_label
        self._rolling_summary = ""
        self._summarized_line_count = 0
        self._consolidation_lock = asyncio.Lock()

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

    def build_user_prompt(self, lines: list[str]) -> str:
        recent = lines[-WINDOW_LINES:]
        if not self._rolling_summary:
            return "\n".join(recent)
        return (
            f"Summary of earlier conversation:\n{self._rolling_summary}\n\n"
            f"Most recent exchange:\n" + "\n".join(recent)
        )

    def schedule_consolidation(self, lines: list[str]) -> None:
        """Fire-and-forget: called after a turn's response has already
        started streaming, never awaited by the turn itself. Skips
        (doesn't queue) if a consolidation is already in flight — the next
        turn's overflow will just fold in a bigger batch instead."""
        pending = len(lines) - self._summarized_line_count - WINDOW_LINES
        if pending < CONSOLIDATION_BUFFER_LINES or self._consolidation_lock.locked():
            return
        asyncio.create_task(self._consolidate(lines))

    async def _consolidate(self, lines: list[str]) -> None:
        async with self._consolidation_lock:
            segment = lines[self._summarized_line_count : len(lines) - WINDOW_LINES]
            if not segment:
                return
            try:
                updated = await model_gateway.run(
                    use_case=SUMMARY_USE_CASE,
                    system_prompt=_SUMMARY_INSTRUCTIONS,
                    user_prompt=(
                        f"Existing summary:\n{self._rolling_summary or '(none yet)'}\n\n"
                        f"New transcript chunk to fold in:\n" + "\n".join(segment)
                    ),
                )
            except Exception:
                # Best-effort: a failed background consolidation must never
                # take down the interview. The window still covers recent
                # turns; we just retry consolidating a larger batch next time.
                logger.exception("voice_interview_summary consolidation failed, will retry later")
                return
            self._rolling_summary = updated
            self._summarized_line_count = len(lines) - WINDOW_LINES


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
        gateway_llm: GatewayLLM = self._llm  # type: ignore[assignment]
        lines = extract_transcript_lines(
            self._chat_ctx, user_label="Candidate", assistant_label="Interviewer"
        )
        user_prompt = gateway_llm.build_user_prompt(lines)

        # See llm_streaming.py's extract_pending_instructions docstring: a
        # generate_reply(instructions=...) call (opening greeting, silence
        # nudge — see conversation_start.py) reaches us as a system-role
        # chat_ctx message, not a parameter — without surfacing it, the
        # model gets no cue that this turn is a nudge/opening rather than a
        # normal continuation, and no real transcript to react to.
        pending_instructions = extract_pending_instructions(self._chat_ctx)
        if pending_instructions:
            user_prompt = (
                f"[One-off instruction for this turn only: {pending_instructions}]\n\n"
                f"{user_prompt}"
            )

        # Dev-dashboard-only: the actual context content sent for this turn,
        # not just its size — see model_gateway/gateway.py's context_detail
        # docstring note and dev_tools/metrics_dashboard.py's click-to-expand.
        # Gated behind DEV_METRICS_ENABLED (see dev_metrics.py's module
        # docstring) since this includes raw candidate/interviewer speech —
        # must default off outside a developer's own local run.
        context_detail = (
            {
                "session": gateway_llm._session_label,
                "recent_window_lines": lines[-WINDOW_LINES:],
                "summary": gateway_llm._rolling_summary or None,
                "summarized_line_count": gateway_llm._summarized_line_count,
            }
            if is_dev_metrics_enabled()
            else None
        )

        reply_pieces: list[str] = []
        async for chunk in stream_turn_chunks(
            use_case=USE_CASE,
            system_prompt=self._system_prompt,
            user_prompt=user_prompt,
            context_detail=context_detail,
        ):
            reply_pieces.append(chunk.delta.content or "")
            self._event_ch.send_nowait(chunk)

        # Dev-dashboard-only live transcript snapshot — see
        # dev_tools/metrics_dashboard.py's "Live Transcript" tab. Same
        # DEV_METRICS_ENABLED gate as context_detail above: this is raw
        # candidate/interviewer speech written to a local file.
        if is_dev_metrics_enabled():
            write_transcript_snapshot(
                gateway_llm._session_label, [*lines, f"Interviewer: {''.join(reply_pieces)}"]
            )

        # Scheduled after streaming is done, not awaited — runs in the
        # background while the candidate is speaking their next answer, so
        # it never adds latency to a turn anyone is waiting on.
        gateway_llm.schedule_consolidation(lines)
