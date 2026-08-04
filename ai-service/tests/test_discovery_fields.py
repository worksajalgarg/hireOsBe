from app.voice_agent.discovery_fields import (
    DiscoveryFields,
    format_state_for_prompt,
    merge,
    missing_field_labels,
)


def test_missing_field_labels_lists_every_unfilled_field() -> None:
    state = DiscoveryFields()
    assert len(missing_field_labels(state)) == 16


def test_missing_field_labels_excludes_filled_fields() -> None:
    state = DiscoveryFields(hiring_reason="backfill", business_problem="scaling support")
    missing = missing_field_labels(state)
    assert "Why hiring now" not in missing
    assert "Business problem" not in missing
    assert len(missing) == 14


def test_merge_fills_in_new_values_without_touching_existing_ones() -> None:
    old = DiscoveryFields(hiring_reason="backfill")
    new = DiscoveryFields(business_problem="scaling support")
    merged = merge(old, new)
    assert merged.hiring_reason == "backfill"
    assert merged.business_problem == "scaling support"


def test_merge_latest_wins_on_revision() -> None:
    old = DiscoveryFields(hiring_reason="backfill")
    new = DiscoveryFields(hiring_reason="actually it's a new headcount for growth")
    merged = merge(old, new)
    assert merged.hiring_reason == "actually it's a new headcount for growth"


def test_merge_null_never_erases_existing_value() -> None:
    """The extractor is instructed to return null for anything not addressed
    in the new transcript segment — null must mean 'no new information,'
    never 'clear this field.'"""
    old = DiscoveryFields(hiring_reason="backfill", business_problem="scaling support")
    new = DiscoveryFields(hiring_reason=None, business_problem=None)
    merged = merge(old, new)
    assert merged.hiring_reason == "backfill"
    assert merged.business_problem == "scaling support"


def test_format_state_for_prompt_reports_nothing_captured_at_start() -> None:
    text = format_state_for_prompt(DiscoveryFields())
    assert "Nothing captured yet" in text
    assert "Still missing" in text


def test_format_state_for_prompt_reports_completion() -> None:
    filled = {name: "answered" for name in DiscoveryFields.model_fields}
    text = format_state_for_prompt(DiscoveryFields(**filled))
    assert "Still missing" not in text
    assert "consider closing the call" in text
