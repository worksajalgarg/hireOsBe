"""The structured intake record the Hiring Manager Discovery Agent builds up
over a call (see discovery_llm.py). Defined once here and shared by the
prompt builder (hiring_manager_prompts.py) and the per-turn extractor
(discovery_llm.py) so both agree on exactly the same 16 fields and labels —
the whole point of tracking this as explicit state instead of leaving
completeness to conversational memory (see discovery_llm.py's module
docstring for why memory alone isn't enough over a long call).

Every field is optional free text (not lists/enums): hiring managers
describe things in prose, and normalizing shape isn't this agent's job —
the downstream role_intake_scorecard use case (see use_case_policy.py) is
where anything more structured than "the manager's own words" would get
derived, with human review in between (see hireOsBe/CLAUDE.md's Role
Context Agent boundary: this agent never publishes a rubric itself).
"""

from pydantic import BaseModel

# (field name, human-readable label, short guidance for what belongs here) —
# single source of truth for the prompt's checklist, the extractor's
# instructions, and the final read-back summary.
FIELD_SPECS: list[tuple[str, str, str]] = [
    ("hiring_reason", "Why hiring now", "backfill, growth, new function, etc."),
    ("business_problem", "Business problem", "what business problem this hire solves"),
    ("success_definition", "Success definition", "what success looks like, as an outcome"),
    ("responsibilities", "Responsibilities", "day-to-day plus strategic responsibilities"),
    ("required_skills", "Required skills", "must-have skills/experience"),
    ("preferred_skills", "Preferred skills", "nice-to-have skills/experience"),
    ("team_structure", "Team structure", "reporting line, team size/composition"),
    ("collaboration", "Collaboration", "key cross-functional collaborators"),
    ("decision_authority", "Decision authority", "what this person owns vs. escalates"),
    ("day_30_60_90", "30/60/90-day expectations", "concrete early milestones"),
    ("success_metrics", "Success metrics", "how success will be measured"),
    ("failure_modes", "Failure modes", "what 'not working out' looks like"),
    ("interview_process", "Interview process", "planned stages/panel"),
    ("evaluation_criteria", "Evaluation criteria", "how candidates get compared"),
    (
        "compensation_constraints",
        "Compensation constraints",
        "budget/band, negotiability, hard constraints",
    ),
    ("hiring_timeline", "Hiring timeline", "target start date, hard deadlines"),
]

FIELD_NAMES = [name for name, _, _ in FIELD_SPECS]
FIELD_LABELS = {name: label for name, label, _ in FIELD_SPECS}


class DiscoveryFields(BaseModel):
    hiring_reason: str | None = None
    business_problem: str | None = None
    success_definition: str | None = None
    responsibilities: str | None = None
    required_skills: str | None = None
    preferred_skills: str | None = None
    team_structure: str | None = None
    collaboration: str | None = None
    decision_authority: str | None = None
    day_30_60_90: str | None = None
    success_metrics: str | None = None
    failure_modes: str | None = None
    interview_process: str | None = None
    evaluation_criteria: str | None = None
    compensation_constraints: str | None = None
    hiring_timeline: str | None = None


def missing_field_labels(state: DiscoveryFields) -> list[str]:
    return [FIELD_LABELS[name] for name in FIELD_NAMES if getattr(state, name) is None]


def merge(old: DiscoveryFields, new: DiscoveryFields) -> DiscoveryFields:
    """'Latest wins,' but only for fields the extractor actually returned a
    value for this turn — the extraction prompt is instructed to return null
    for anything not addressed in the new transcript segment, so a null here
    means "no new information," not "clear this field." Never lets an
    extraction turn silently erase something already collected."""
    merged = old.model_copy()
    for name in FIELD_NAMES:
        new_value = getattr(new, name)
        if new_value is not None:
            setattr(merged, name, new_value)
    return merged


def format_state_for_prompt(state: DiscoveryFields) -> str:
    filled = [
        f"- {FIELD_LABELS[name]}: {getattr(state, name)}"
        for name in FIELD_NAMES
        if getattr(state, name) is not None
    ]
    missing = missing_field_labels(state)
    parts = []
    if filled:
        parts.append("Captured so far:\n" + "\n".join(filled))
    else:
        parts.append("Nothing captured yet — this is the start of the conversation.")
    if missing:
        parts.append("Still missing: " + ", ".join(missing))
    else:
        parts.append("Every field has at least a preliminary answer — consider closing the call.")
    return "\n\n".join(parts)


def format_summary_for_readback(state: DiscoveryFields) -> str:
    lines = [
        f"{FIELD_LABELS[name]}: {getattr(state, name) or '(not yet provided — TBD)'}"
        for name in FIELD_NAMES
    ]
    return "\n".join(lines)
