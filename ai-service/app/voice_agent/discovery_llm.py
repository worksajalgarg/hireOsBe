"""A livekit-agents LLM plugin for the Hiring Manager Discovery Agent —
structurally the sibling of gateway_llm.py's GatewayLLM (candidate
interview), sharing its model-gateway-routing and chunk-streaming plumbing
(see llm_streaming.py) but replacing the candidate agent's sliding-window
+ prose-summary memory with structured slot-tracking (see discovery_fields.py).

Why slot-state instead of a prose summary here: this agent's entire purpose
is producing a complete, accurate structured record by the end of the call —
relying on conversational memory alone (or even a prose summary) to track
16 discrete topics risks exactly the failure this design avoids: repeat
questions, dropped follow-ups, or a final summary the model has to
reconstruct from scratch. Explicit state, re-injected into every turn's
prompt, is what actually prevents that.

Extraction runs after every single turn, not buffered like the candidate
agent's every-~4-turns summary consolidation — a stale slot-state fed into
the very next turn directly causes the repeat-question bug this feature
exists to prevent, so a fresher-but-more-frequent background call is the
right tradeoff here (this agent's calls are also much shorter than a
candidate interview, so the extra background LLM calls are bounded).
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
from .discovery_fields import DiscoveryFields, format_state_for_prompt, merge
from .llm_streaming import (
    extract_pending_instructions,
    extract_transcript_lines,
    stream_turn_chunks,
)

logger = logging.getLogger("voice_agent")

USE_CASE = "role_discovery_turn"
EXTRACTION_USE_CASE = "role_discovery_extraction"

_EXTRACTION_INSTRUCTIONS = """You are extracting structured hiring-intake fields from an \
ongoing discovery conversation between an AI agent and a hiring manager. You are given the \
fields already captured (as JSON, possibly with nulls) and the full transcript so far. Return \
a JSON object with the current value for every field.

For a field the transcript doesn't address at all, or whose value hasn't changed since it was \
last captured, return null for that field — do not guess, and do not invent a value the hiring \
manager didn't actually state. If the hiring manager has explicitly revised an earlier answer, \
return the latest version, not the original. Never include a hire/reject judgment, a score, or \
anything beyond the facts the hiring manager actually stated."""


class DiscoveryLLM(llm.LLM):
    """Wraps the model gateway as a livekit-agents LLM for the Hiring
    Manager Discovery Agent. One instance lives for the whole call (see
    session.py), so the collected state persists across turns."""

    def __init__(self, *, system_prompt: str, session_label: str = "unknown") -> None:
        super().__init__()
        self._system_prompt = system_prompt
        self._session_label = session_label
        self._state = DiscoveryFields()
        self._extraction_lock = asyncio.Lock()
        self._pending_lines: list[str] | None = None
        self._last_processed_lines: list[str] | None = None

    @property
    def model(self) -> str:
        return USE_CASE

    @property
    def provider(self) -> str:
        return "hireos-model-gateway"

    @property
    def state(self) -> DiscoveryFields:
        """The structured intake record collected so far — this is also
        what the closing "read back the summary" turn formats for the
        hiring manager, and what a future platform-side integration would
        persist (see the plan's explicitly-out-of-scope note on that)."""
        return self._state

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
        return DiscoveryLLMStream(
            self,
            chat_ctx=chat_ctx,
            tools=tools or [],
            conn_options=conn_options,
            system_prompt=self._system_prompt,
        )

    def build_user_prompt(self, lines: list[str]) -> str:
        # Calls here are short (15-20 minute role-intake conversations), so
        # unlike the candidate agent's sliding window (built for much longer
        # interviews), the full transcript is sent every turn — accuracy of
        # the structured extraction matters more than shaving tokens off a
        # call this length.
        transcript = "\n".join(lines) if lines else "(conversation hasn't started yet)"
        return f"Transcript so far:\n{transcript}\n\n{format_state_for_prompt(self._state)}"

    def schedule_extraction(self, lines: list[str]) -> None:
        """Fire-and-forget, called after a turn's response has already
        started streaming. Uses a drain loop rather than one task per turn:
        if extraction is still running when a later turn finishes, this
        just updates what "latest" means — the in-flight extraction keeps
        running against its own snapshot, and the loop immediately picks up
        the newest transcript afterward. A slow extraction call can never
        pile up an unbounded backlog of tasks, and turns are still always
        eventually reflected, just possibly coalesced with the next one."""
        if not lines or lines == self._last_processed_lines:
            return
        self._pending_lines = lines
        if not self._extraction_lock.locked():
            asyncio.create_task(self._drain_extractions())

    async def _drain_extractions(self) -> None:
        async with self._extraction_lock:
            while (
                self._pending_lines is not None
                and self._pending_lines != self._last_processed_lines
            ):
                lines = self._pending_lines
                await self._extract(lines)
                self._last_processed_lines = lines

    async def _extract(self, lines: list[str]) -> None:
        try:
            updated = await model_gateway.run_structured(
                use_case=EXTRACTION_USE_CASE,
                system_prompt=_EXTRACTION_INSTRUCTIONS,
                user_prompt=(
                    f"Fields already captured:\n{self._state.model_dump_json()}\n\n"
                    "Full transcript so far:\n" + "\n".join(lines)
                ),
                schema=DiscoveryFields,
            )
        except Exception:
            # Best-effort and non-destructive: a failed extraction (both
            # provider attempts exhausted — see gateway.py's run_structured)
            # must never clear or corrupt already-collected state. The next
            # turn's schedule_extraction() just tries again from scratch.
            logger.exception("role_discovery_extraction failed, keeping prior state")
            return
        self._state = merge(self._state, updated)


class DiscoveryLLMStream(llm.LLMStream):
    def __init__(
        self,
        llm_: DiscoveryLLM,
        *,
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool],
        conn_options: APIConnectOptions,
        system_prompt: str,
    ) -> None:
        super().__init__(llm_, chat_ctx=chat_ctx, tools=tools, conn_options=conn_options)
        self._system_prompt = system_prompt

    async def _run(self) -> None:
        discovery_llm: DiscoveryLLM = self._llm  # type: ignore[assignment]
        lines = extract_transcript_lines(
            self._chat_ctx, user_label="Hiring Manager", assistant_label="Agent"
        )
        user_prompt = discovery_llm.build_user_prompt(lines)

        # See llm_streaming.py's extract_pending_instructions docstring —
        # same reasoning as gateway_llm.py: without this, a nudge/opening
        # generate_reply(instructions=...) call is indistinguishable from a
        # normal continuation, which is how the model ends up free-running.
        pending_instructions = extract_pending_instructions(self._chat_ctx)
        if pending_instructions:
            user_prompt = (
                f"[One-off instruction for this turn only: {pending_instructions}]\n\n"
                f"{user_prompt}"
            )

        async for chunk in stream_turn_chunks(
            use_case=USE_CASE,
            system_prompt=self._system_prompt,
            user_prompt=user_prompt,
        ):
            self._event_ch.send_nowait(chunk)

        # Scheduled after streaming is done, not awaited — runs in the
        # background while the hiring manager is speaking their next
        # answer, so it never adds latency to a turn anyone is waiting on.
        discovery_llm.schedule_extraction(lines)
