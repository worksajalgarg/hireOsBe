import json
from pathlib import Path

from app.voice_agent.prompts import _compact_resume_context, build_interview_system_prompt

_SAMPLE_RESUME = (
    Path(__file__).resolve().parent.parent / "app/voice_agent/fixtures/sample_resume.json"
).read_text()


def test_compact_resume_keeps_every_achievement_per_role() -> None:
    compact = _compact_resume_context(_SAMPLE_RESUME)
    data = json.loads(_SAMPLE_RESUME)
    for role in data["experience"]:
        for achievement in role["achievements"]:
            assert achievement in compact


def test_compact_resume_includes_education() -> None:
    compact = _compact_resume_context(_SAMPLE_RESUME)
    data = json.loads(_SAMPLE_RESUME)
    edu = data["education"][0]
    assert edu["degree"] in compact
    assert edu["institution"] in compact
    assert str(edu["year"]) in compact


def test_compact_resume_respects_overall_length_cap() -> None:
    bloated = {
        "name": "Test Candidate",
        "skills": ["x"],
        "experience": [
            {
                "title": f"Role {i}",
                "company": f"Company {i}",
                "duration": "2020 - 2021",
                "achievements": ["A very long achievement description. " * 20],
            }
            for i in range(50)
        ],
    }
    compact = _compact_resume_context(json.dumps(bloated))
    assert len(compact) <= 4000


def test_build_interview_system_prompt_includes_compacted_resume() -> None:
    prompt = build_interview_system_prompt(_SAMPLE_RESUME)
    assert "idempotency-key" in prompt
    assert "VIT Vellore" in prompt
