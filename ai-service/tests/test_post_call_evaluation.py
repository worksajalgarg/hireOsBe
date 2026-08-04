import asyncio

from app.voice_agent import post_call_evaluation
from app.voice_agent.evaluation_schema import EvaluationLLMOutput


def _run(coro):
    return asyncio.run(coro)


def test_short_transcript_returns_insufficient_data_without_calling_the_llm(monkeypatch) -> None:
    called = False

    async def fake_run_structured(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("should not be called for a too-short transcript")

    monkeypatch.setattr(
        "app.voice_agent.post_call_evaluation.model_gateway.run_structured", fake_run_structured
    )

    result = _run(
        post_call_evaluation.evaluate_interview(
            candidate_ref="cand-1", transcript_lines=["Candidate: hi"]
        )
    )

    assert called is False
    assert result.recommendation == "insufficient_data"
    assert result.candidate_ref == "cand-1"
    assert result.topics == []


def test_llm_failure_falls_back_to_insufficient_data_never_raises(monkeypatch) -> None:
    async def fake_run_structured(**kwargs):
        raise RuntimeError("provider chain exhausted")

    monkeypatch.setattr(
        "app.voice_agent.post_call_evaluation.model_gateway.run_structured", fake_run_structured
    )

    long_transcript = [
        f"Candidate: answer number {i} with plenty of detail here" for i in range(10)
    ]
    result = _run(
        post_call_evaluation.evaluate_interview(
            candidate_ref="cand-2", transcript_lines=long_transcript
        )
    )

    assert result.recommendation == "insufficient_data"
    assert result.candidate_ref == "cand-2"


def test_successful_evaluation_maps_llm_output_and_fills_metadata(monkeypatch) -> None:
    llm_output = EvaluationLLMOutput(
        recommendation="strong_review",
        overall_assessment="Strong candidate.",
        topics=[],
    )

    async def fake_run_structured(**kwargs):
        return llm_output

    monkeypatch.setattr(
        "app.voice_agent.post_call_evaluation.model_gateway.run_structured", fake_run_structured
    )

    long_transcript = [
        f"Candidate: answer number {i} with plenty of detail here" for i in range(10)
    ]
    result = _run(
        post_call_evaluation.evaluate_interview(
            candidate_ref="cand-3", transcript_lines=long_transcript
        )
    )

    assert result.recommendation == "strong_review"
    assert result.overall_assessment == "Strong candidate."
    assert result.candidate_ref == "cand-3"
    assert result.model_version == f"model_gateway:{post_call_evaluation.USE_CASE}"
