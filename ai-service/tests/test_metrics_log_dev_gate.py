from pathlib import Path

from app.model_gateway import metrics_log


def test_append_metric_skips_write_when_dev_metrics_disabled(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DEV_METRICS_ENABLED", "false")
    monkeypatch.setattr(metrics_log, "METRICS_LOG_PATH", tmp_path / "model_gateway_metrics.jsonl")

    metrics_log.append_metric({"use_case": "test"})

    assert not metrics_log.METRICS_LOG_PATH.exists()


def test_append_metric_writes_when_dev_metrics_enabled(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DEV_METRICS_ENABLED", "true")
    monkeypatch.setattr(metrics_log, "METRICS_LOG_PATH", tmp_path / "model_gateway_metrics.jsonl")

    metrics_log.append_metric({"use_case": "test"})

    assert metrics_log.METRICS_LOG_PATH.exists()


def test_is_dev_metrics_enabled_defaults_false(monkeypatch) -> None:
    monkeypatch.delenv("DEV_METRICS_ENABLED", raising=False)
    assert metrics_log.is_dev_metrics_enabled() is False


def test_is_dev_metrics_enabled_reexported_from_voice_agent_dev_metrics() -> None:
    from app.voice_agent.dev_metrics import is_dev_metrics_enabled

    assert is_dev_metrics_enabled is metrics_log.is_dev_metrics_enabled
