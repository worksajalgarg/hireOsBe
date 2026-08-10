"""Two related conversation-start concerns shared by both voice personas
(candidate interview and hiring manager discovery):

1. The agent speaks first when a call connects, instead of sitting silent
   until the human speaks. livekit-agents' `Agent.on_enter()` default is a
   no-op (confirmed in the installed package's agent.py) — neither persona
   opens on its own without this override.

2. If the human goes silent mid-call, the agent proactively checks in
   rather than waiting indefinitely. Built on AgentSession's existing
   `user_away_timeout` / `user_state_changed` event (fires "away" after the
   human has been silent for that many seconds while the agent is
   listening — 15s by default) rather than hand-rolling a silence timer.
"""

import logging

from livekit.agents import Agent, AgentSession
from livekit.agents.voice import UserStateChangedEvent

logger = logging.getLogger("voice_agent")

# After this many consecutive silent nudges with no reply in between, stop
# prompting — an unbounded "are you still there?" loop isn't useful once
# it's clear the human has disconnected or stepped away for good. A human
# reviewer picks this up from the recording/transcript afterward, the same
# way any other mid-call issue is handled (see hireOsBe/CLAUDE.md's
# Responsible AI constraint: a failed connection must never silently lower
# a candidate's score — it's a review-flag situation, not something this
# agent should paper over by nudging forever).
_MAX_CONSECUTIVE_NUDGES = 2


class OpeningAgent(Agent):
    """An Agent that speaks first on entering the session. `instructions`
    is the persona's full system prompt (unchanged); `opening_instructions`
    is a short one-off instruction for just the very first thing the agent
    says — kept separate from the system prompt so it doesn't have to be
    re-stated on every subsequent turn."""

    def __init__(self, *, instructions: str, opening_instructions: str) -> None:
        super().__init__(instructions=instructions)
        self._opening_instructions = opening_instructions

    async def on_enter(self) -> None:
        self.session.generate_reply(instructions=self._opening_instructions)


def register_silence_handling(session: AgentSession, *, nudge_instructions: str) -> None:
    """Subscribes to the session's user_state_changed event and nudges the
    human when they've gone quiet, up to _MAX_CONSECUTIVE_NUDGES in a row.
    The counter resets as soon as the human speaks again, so a single
    long-thinking pause followed by a real answer doesn't count against a
    later, separate silence later in the call."""
    consecutive_nudges = 0

    def _on_user_state_changed(ev: UserStateChangedEvent) -> None:
        nonlocal consecutive_nudges
        if ev.new_state == "away":
            if consecutive_nudges >= _MAX_CONSECUTIVE_NUDGES:
                logger.warning(
                    "participant silent past nudge limit (%d), no further prompts",
                    _MAX_CONSECUTIVE_NUDGES,
                )
                return
            consecutive_nudges += 1
            session.generate_reply(instructions=nudge_instructions)
        elif ev.new_state == "speaking":
            consecutive_nudges = 0

    session.on("user_state_changed", _on_user_state_changed)
