from pathlib import Path

import pytest

from app.model_gateway.routing_config import load_routing_config
from app.model_gateway.use_case_policy import USE_CASE_POLICIES

_ROUTING_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "model_routing.yaml"


@pytest.fixture(autouse=True, scope="session")
def _load_real_routing_config() -> None:
    """USE_CASE_POLICIES starts empty (see use_case_policy.py) and is
    normally populated at process startup by worker.py/main.py. Tests that
    call get_policy()/apply_provider_priority() against real use-case names
    (e.g. test_use_case_policy_priority.py) need it populated the same way
    production is, from the real config/model_routing.yaml — not a fixture
    file, so those tests keep asserting against actual production chains."""
    USE_CASE_POLICIES.update(load_routing_config(_ROUTING_CONFIG_PATH))
