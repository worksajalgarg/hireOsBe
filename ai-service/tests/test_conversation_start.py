from livekit.agents import Agent
from livekit.agents.voice import UserStateChangedEvent

from app.voice_agent.conversation_start import (
    _MAX_CONSECUTIVE_NUDGES,
    OpeningAgent,
    register_silence_handling,
)


def test_opening_agent_is_a_regular_agent_with_stored_opening_instructions() -> None:
    agent = OpeningAgent(instructions="be terse", opening_instructions="say hello")
    assert isinstance(agent, Agent)
    assert agent._opening_instructions == "say hello"


class _FakeSession:
    def __init__(self) -> None:
        self._handlers: dict[str, object] = {}
        self.generate_reply_calls: list[str] = []

    def on(self, event: str, handler) -> None:
        self._handlers[event] = handler

    def fire(self, event: str, ev: object) -> None:
        self._handlers[event](ev)

    def generate_reply(self, *, instructions: str):
        self.generate_reply_calls.append(instructions)


def _away_event() -> UserStateChangedEvent:
    return UserStateChangedEvent(old_state="listening", new_state="away")


def _speaking_event() -> UserStateChangedEvent:
    return UserStateChangedEvent(old_state="listening", new_state="speaking")


def test_silence_handling_nudges_on_away() -> None:
    session = _FakeSession()
    register_silence_handling(session, nudge_instructions="are you there?")
    session.fire("user_state_changed", _away_event())
    assert session.generate_reply_calls == ["are you there?"]


def test_silence_handling_stops_after_max_consecutive_nudges() -> None:
    session = _FakeSession()
    register_silence_handling(session, nudge_instructions="are you there?")
    for _ in range(_MAX_CONSECUTIVE_NUDGES + 3):
        session.fire("user_state_changed", _away_event())
    assert len(session.generate_reply_calls) == _MAX_CONSECUTIVE_NUDGES


def test_silence_handling_resets_counter_once_user_speaks() -> None:
    session = _FakeSession()
    register_silence_handling(session, nudge_instructions="are you there?")
    for _ in range(_MAX_CONSECUTIVE_NUDGES):
        session.fire("user_state_changed", _away_event())
    session.fire("user_state_changed", _speaking_event())
    session.fire("user_state_changed", _away_event())
    # Without the reset, this nudge would have been suppressed as past the cap.
    assert len(session.generate_reply_calls) == _MAX_CONSECUTIVE_NUDGES + 1
