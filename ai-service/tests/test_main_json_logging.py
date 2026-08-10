"""Verifies app/main.py's _configure_logging(): structured JSON-to-stdout
in non-dev APP_ENV, Python's default logging left alone in dev — the
FastAPI-process counterpart to what voice_agent/worker.py already gets for
free from livekit-agents' own cli.run_app()/setup_logging()."""

import importlib
import logging
import sys

from livekit.agents.cli.log import JsonFormatter


def _reload_main_with_app_env(monkeypatch, value: str | None):
    if value is None:
        monkeypatch.delenv("APP_ENV", raising=False)
    else:
        monkeypatch.setenv("APP_ENV", value)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    sys.modules.pop("app.main", None)
    return importlib.import_module("app.main")


def _snapshot_root_handlers():
    root = logging.getLogger()
    return list(root.handlers), root.level


def _restore_root_handlers(snapshot):
    handlers, level = snapshot
    root = logging.getLogger()
    root.handlers = handlers
    root.setLevel(level)


def test_adds_json_formatter_handler_in_non_dev_env(monkeypatch) -> None:
    snapshot = _snapshot_root_handlers()
    try:
        _reload_main_with_app_env(monkeypatch, "production")
        root = logging.getLogger()
        json_handlers = [h for h in root.handlers if isinstance(h.formatter, JsonFormatter)]
        assert len(json_handlers) == 1
    finally:
        _restore_root_handlers(snapshot)


def test_does_not_add_handler_in_dev_env(monkeypatch) -> None:
    snapshot = _snapshot_root_handlers()
    try:
        before = len(logging.getLogger().handlers)
        _reload_main_with_app_env(monkeypatch, "local")
        after = len(logging.getLogger().handlers)
        assert after == before
    finally:
        _restore_root_handlers(snapshot)
