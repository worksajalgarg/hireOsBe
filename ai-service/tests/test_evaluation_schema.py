from app.voice_agent.evaluation_schema import InterviewEvaluationSummary, TopicEvaluation


def test_serializes_to_camel_case_matching_platform_dto() -> None:
    summary = InterviewEvaluationSummary(
        candidate_ref="cand-1",
        recommendation="review",
        overall_assessment="Solid candidate overall.",
        topics=[
            TopicEvaluation(
                topic="Background",
                question_asked="Tell me about your background.",
                response_summary="Five years building backend systems.",
                evidence_strength="strong",
                supporting_evidence=["Described specific projects in detail"],
                missing_evidence=[],
            )
        ],
        model_version="model_gateway:interview_evaluation",
        generated_at="2026-08-02T00:00:00+00:00",
    )

    dumped = summary.model_dump(by_alias=True)

    assert dumped["candidateRef"] == "cand-1"
    assert dumped["overallAssessment"] == "Solid candidate overall."
    assert dumped["modelVersion"] == "model_gateway:interview_evaluation"
    assert dumped["generatedAt"] == "2026-08-02T00:00:00+00:00"
    topic = dumped["topics"][0]
    assert topic["questionAsked"] == "Tell me about your background."
    assert topic["responseSummary"] == "Five years building backend systems."
    assert topic["evidenceStrength"] == "strong"
    assert topic["supportingEvidence"] == ["Described specific projects in detail"]
    assert topic["missingEvidence"] == []
