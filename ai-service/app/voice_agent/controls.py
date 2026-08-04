"""Candidate-facing call controls (repeat / clarify / pause / resume),
delivered over the LiveKit data channel rather than a REST call — the
frontend's InterviewControls component publishes a small JSON payload on
the "interview-controls" topic, and this handler reacts by driving the
AgentSession directly (generate_reply/interrupt/say), no model_gateway
boundary crossed for any of it.
"""

from __future__ import annotations

import json
import logging

from livekit import rtc
from livekit.agents import AgentSession

logger = logging.getLogger("voice_agent")

CONTROLS_TOPIC = "interview-controls"

_REPEAT_INSTRUCTIONS = (
    "The candidate asked you to repeat your previous question. Repeat it in the same words, "
    "without adding anything new."
)
_CLARIFY_INSTRUCTIONS = (
    "The candidate asked you to clarify your previous question. Rephrase it more simply "
    "and clearly, without changing what it's asking."
)
_PAUSE_MESSAGE = "Sure, take your time. Let me know when you're ready to continue."
_RESUME_MESSAGE = "Great, let's continue — go ahead whenever you're ready."


def register_control_handlers(room: rtc.Room, session: AgentSession) -> None:
    def on_data_received(packet: rtc.DataPacket) -> None:
        if packet.topic != CONTROLS_TOPIC:
            return

        try:
            payload = json.loads(packet.data.decode("utf-8"))
            action = payload.get("action")
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.warning("Ignoring malformed %s payload", CONTROLS_TOPIC)
            return

        logger.info("interview control received: %s", action)

        if action == "repeat":
            session.generate_reply(instructions=_REPEAT_INSTRUCTIONS)
        elif action == "clarify":
            session.generate_reply(instructions=_CLARIFY_INSTRUCTIONS)
        elif action == "pause":
            session.interrupt()
            session.say(_PAUSE_MESSAGE)
        elif action == "resume":
            session.say(_RESUME_MESSAGE)
        else:
            logger.warning("Unknown %s action: %r", CONTROLS_TOPIC, action)

    room.on("data_received", on_data_received)
