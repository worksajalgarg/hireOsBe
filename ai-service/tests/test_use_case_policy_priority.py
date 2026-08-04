import copy

from app.model_gateway.providers import Provider
from app.model_gateway.use_case_policy import (
    USE_CASE_POLICIES,
    apply_provider_priority,
    get_policy,
)


def _snapshot():
    return copy.deepcopy(USE_CASE_POLICIES)


def _restore(snapshot):
    USE_CASE_POLICIES.clear()
    USE_CASE_POLICIES.update(snapshot)


def test_apply_provider_priority_reorders_matching_use_case() -> None:
    snapshot = _snapshot()
    try:
        before = [c.provider for c in get_policy("voice_interview_turn").chain]
        assert before == [Provider.GEMINI, Provider.GROQ, Provider.OPENROUTER]

        apply_provider_priority(["voice_interview_turn"], [Provider.GROQ, Provider.GEMINI])

        after = [c.provider for c in get_policy("voice_interview_turn").chain]
        assert after == [Provider.GROQ, Provider.GEMINI, Provider.OPENROUTER]
    finally:
        _restore(snapshot)


def test_apply_provider_priority_keeps_unmentioned_providers_in_relative_order() -> None:
    snapshot = _snapshot()
    try:
        # Only mention GROQ — GEMINI and OPENROUTER should stay in their
        # original relative order, appended after.
        apply_provider_priority(["voice_interview_turn"], [Provider.GROQ])
        after = [c.provider for c in get_policy("voice_interview_turn").chain]
        assert after == [Provider.GROQ, Provider.GEMINI, Provider.OPENROUTER]
    finally:
        _restore(snapshot)


def test_apply_provider_priority_preserves_model_and_timeout() -> None:
    snapshot = _snapshot()
    try:
        policy = get_policy("voice_interview_turn")
        before = {c.provider: (c.model, c.timeout_s) for c in policy.chain}
        apply_provider_priority(["voice_interview_turn"], [Provider.GROQ, Provider.GEMINI])
        policy = get_policy("voice_interview_turn")
        after = {c.provider: (c.model, c.timeout_s) for c in policy.chain}
        assert before == after
    finally:
        _restore(snapshot)


def test_apply_provider_priority_only_touches_named_use_cases() -> None:
    snapshot = _snapshot()
    try:
        before = [c.provider for c in get_policy("resume_parsing").chain]
        apply_provider_priority(["voice_interview_turn"], [Provider.GEMINI, Provider.GROQ])
        after = [c.provider for c in get_policy("resume_parsing").chain]
        assert before == after
    finally:
        _restore(snapshot)


def test_apply_provider_priority_is_idempotent() -> None:
    snapshot = _snapshot()
    try:
        order = [Provider.GEMINI, Provider.GROQ, Provider.OPENROUTER]
        apply_provider_priority(["voice_interview_turn"], order)
        once = [c.provider for c in get_policy("voice_interview_turn").chain]
        apply_provider_priority(["voice_interview_turn"], order)
        twice = [c.provider for c in get_policy("voice_interview_turn").chain]
        assert once == twice == order
    finally:
        _restore(snapshot)
