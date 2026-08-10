"""Verifies app/main.py's env guard around the unauthenticated /dev/metrics
dashboard: it must fail CLOSED (not mounted) unless APP_ENV explicitly names
a non-production environment — see main.py's _dev_metrics_dashboard_allowed
and docs/adr note in app/main.py's comment above app.include_router(...)."""

import importlib
import sys

from fastapi.testclient import TestClient


def _reload_main_with_app_env(monkeypatch, value: str | None):
    if value is None:
        monkeypatch.delenv("APP_ENV", raising=False)
    else:
        monkeypatch.setenv("APP_ENV", value)
    # main.py calls load_dotenv() at import time (see its module docstring
    # comment) — without stubbing it out here, reloading the module would
    # repopulate APP_ENV from the real ai-service/.env file (which sets
    # APP_ENV="local" for local dev) whenever the test wants to simulate it
    # being unset/production, defeating the point of this test.
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    sys.modules.pop("app.main", None)
    return importlib.import_module("app.main")


def test_predicate_true_for_known_dev_env_names(monkeypatch) -> None:
    from app.main import _dev_metrics_dashboard_allowed

    for name in ["local", "development", "dev", "LOCAL", " Development "]:
        monkeypatch.setenv("APP_ENV", name)
        assert _dev_metrics_dashboard_allowed() is True, name


def test_predicate_false_when_unset_or_unrecognized(monkeypatch) -> None:
    from app.main import _dev_metrics_dashboard_allowed

    monkeypatch.delenv("APP_ENV", raising=False)
    assert _dev_metrics_dashboard_allowed() is False

    for name in ["", "staging", "production", "prod", "loca"]:
        monkeypatch.setenv("APP_ENV", name)
        assert _dev_metrics_dashboard_allowed() is False, name


def test_router_not_mounted_when_app_env_unset(monkeypatch) -> None:
    module = _reload_main_with_app_env(monkeypatch, None)
    client = TestClient(module.app)
    assert client.get("/dev/metrics").status_code == 404


def test_router_not_mounted_when_app_env_is_production(monkeypatch) -> None:
    module = _reload_main_with_app_env(monkeypatch, "production")
    client = TestClient(module.app)
    assert client.get("/dev/metrics").status_code == 404


def test_router_mounted_when_app_env_is_local(monkeypatch) -> None:
    module = _reload_main_with_app_env(monkeypatch, "local")
    client = TestClient(module.app)
    assert client.get("/dev/metrics").status_code == 200
