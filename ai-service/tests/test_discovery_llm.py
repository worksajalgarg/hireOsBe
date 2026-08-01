import asyncio
from unittest.mock import AsyncMock, patch

from app.voice_agent.discovery_fields import DiscoveryFields
from app.voice_agent.discovery_llm import DiscoveryLLM


def _run(coro):
    return asyncio.run(coro)


def test_extraction_merges_new_fields_into_state() -> None:
    llm = DiscoveryLLM(system_prompt="test")
    with patch(
        "app.voice_agent.discovery_llm.model_gateway.run_structured",
        new=AsyncMock(return_value=DiscoveryFields(hiring_reason="backfill")),
    ):
        _run(llm._extract(["Hiring Manager: We need a backfill for our lead engineer."]))
    assert llm.state.hiring_reason == "backfill"


def test_extraction_failure_leaves_prior_state_untouched() -> None:
    llm = DiscoveryLLM(system_prompt="test")
    llm._state = DiscoveryFields(hiring_reason="backfill")
    with patch(
        "app.voice_agent.discovery_llm.model_gateway.run_structured",
        new=AsyncMock(side_effect=RuntimeError("both providers exhausted")),
    ):
        _run(llm._extract(["Hiring Manager: something new"]))
    # State must be exactly what it was before the failed attempt — a
    # failed extraction must never clear or corrupt already-collected data.
    assert llm.state.hiring_reason == "backfill"
    assert llm.state.business_problem is None


def test_schedule_extraction_skips_duplicate_and_empty_calls() -> None:
    llm = DiscoveryLLM(system_prompt="test")
    calls = []

    async def fake_run_structured(**kwargs):
        calls.append(kwargs["user_prompt"])
        return DiscoveryFields()

    async def scenario():
        with patch(
            "app.voice_agent.discovery_llm.model_gateway.run_structured",
            new=AsyncMock(side_effect=fake_run_structured),
        ):
            lines = ["Hiring Manager: hello"]
            llm.schedule_extraction(lines)
            llm.schedule_extraction([])  # empty — must be a no-op
            llm.schedule_extraction(lines)  # identical to in-flight one — must be a no-op

            # Poll for the actual outcome (calls list growing), not lock
            # state — asyncio.create_task() doesn't run synchronously, so
            # checking "is it locked yet" right after scheduling races
            # against the task not having started at all.
            for _ in range(50):
                if calls:
                    break
                await asyncio.sleep(0.01)

    _run(scenario())
    assert len(calls) == 1
