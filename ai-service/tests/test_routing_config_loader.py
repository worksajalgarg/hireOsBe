from pathlib import Path

import pytest

from app.model_gateway.providers import Provider
from app.model_gateway.routing_config import RoutingConfigError, load_routing_config
from app.model_gateway.use_case_policy import UseCasePolicy

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
_VALID_FIXTURE = _FIXTURES_DIR / "model_routing_valid.yaml"


def test_valid_file_parses_into_use_case_policies() -> None:
    policies = load_routing_config(_VALID_FIXTURE)

    assert set(policies) == {
        "role_intake_scorecard",
        "resume_parsing",
        "evidence_matching",
        "interview_evaluation",
        "candidate_report",
        "voice_interview_turn",
        "voice_interview_summary",
        "role_discovery_turn",
        "role_discovery_extraction",
    }
    turn = policies["voice_interview_turn"]
    assert isinstance(turn, UseCasePolicy)
    assert turn.rationale == "test fixture"
    assert [c.provider for c in turn.chain] == [Provider.OPENROUTER, Provider.GEMINI, Provider.GROQ]
    assert turn.chain[0].model == "nvidia/nemotron-3-nano-30b-a3b:free"
    assert turn.chain[0].timeout_s == 8.0
    assert turn.chain[1].timeout_s is None


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(RoutingConfigError, match="Could not read"):
        load_routing_config(tmp_path / "does_not_exist.yaml")


def test_invalid_yaml_raises(tmp_path: Path) -> None:
    path = tmp_path / "broken.yaml"
    path.write_text("use_cases: [this is not: valid: yaml")
    with pytest.raises(RoutingConfigError, match="not valid YAML"):
        load_routing_config(path)


def _minimal_valid_use_cases() -> dict:
    """A dict with all 9 required use cases, single-tier chains — used as a
    base that individual failure tests mutate one field of."""
    base_chain = [{"provider": "gemini", "model": "gemini-flash-latest"}]
    from app.model_gateway.routing_config import REQUIRED_USE_CASES

    return {
        uc: {"chain": list(base_chain), "rationale": "r"} for uc in REQUIRED_USE_CASES
    }


def _write_yaml(path: Path, data: dict) -> None:
    import yaml

    path.write_text(yaml.safe_dump(data))


def test_unknown_provider_raises(tmp_path: Path) -> None:
    data = _minimal_valid_use_cases()
    data["resume_parsing"]["chain"] = [{"provider": "bogus", "model": "x"}]
    path = tmp_path / "config.yaml"
    _write_yaml(path, data)
    with pytest.raises(RoutingConfigError, match="unknown provider 'bogus'"):
        load_routing_config(path)


def test_empty_chain_raises(tmp_path: Path) -> None:
    data = _minimal_valid_use_cases()
    data["resume_parsing"]["chain"] = []
    path = tmp_path / "config.yaml"
    _write_yaml(path, data)
    with pytest.raises(RoutingConfigError, match="at least one entry"):
        load_routing_config(path)


def test_non_positive_timeout_raises(tmp_path: Path) -> None:
    data = _minimal_valid_use_cases()
    data["resume_parsing"]["chain"] = [
        {"provider": "gemini", "model": "gemini-flash-latest", "timeout_s": 0}
    ]
    path = tmp_path / "config.yaml"
    _write_yaml(path, data)
    with pytest.raises(RoutingConfigError, match="timeout_s must be > 0"):
        load_routing_config(path)


def test_duplicate_provider_model_in_chain_raises(tmp_path: Path) -> None:
    data = _minimal_valid_use_cases()
    data["resume_parsing"]["chain"] = [
        {"provider": "gemini", "model": "gemini-flash-latest"},
        {"provider": "gemini", "model": "gemini-flash-latest"},
    ]
    path = tmp_path / "config.yaml"
    _write_yaml(path, data)
    with pytest.raises(RoutingConfigError, match="duplicate"):
        load_routing_config(path)


def test_missing_required_use_case_raises(tmp_path: Path) -> None:
    data = _minimal_valid_use_cases()
    del data["resume_parsing"]
    path = tmp_path / "config.yaml"
    _write_yaml(path, data)
    with pytest.raises(RoutingConfigError, match="missing required use case"):
        load_routing_config(path)


def test_non_mapping_root_raises(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("- just\n- a\n- list\n")
    with pytest.raises(RoutingConfigError, match="must be a mapping"):
        load_routing_config(path)
