import asyncio
import json
from pathlib import Path

from app.voice_agent import transcript_delivery

_BASE_URL = "http://platform.local/api/v1"
_SECRET = "s3cr3t"


def _run(coro):
    return asyncio.run(coro)


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.text = ""


class _FakeAsyncClient:
    def __init__(self, response: _FakeResponse, *, raises: Exception | None = None) -> None:
        self._response = response
        self._raises = raises
        self.posted_to: str | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, headers=None):  # noqa: A002 -- matches httpx's signature
        self.posted_to = url
        if self._raises:
            raise self._raises
        return self._response


def _patch_client(monkeypatch, tmp_path: Path, *, status_code: int = 200, raises=None):
    monkeypatch.setattr(transcript_delivery, "OUTBOX_DIR", tmp_path)
    client = _FakeAsyncClient(_FakeResponse(status_code), raises=raises)
    monkeypatch.setattr(transcript_delivery.httpx, "AsyncClient", lambda *a, **k: client)
    return client


def test_deliver_transcript_removes_outbox_file_on_success(monkeypatch, tmp_path: Path) -> None:
    _patch_client(monkeypatch, tmp_path, status_code=200)

    _run(
        transcript_delivery.deliver_transcript(
            "session-1", {"tenantId": "t1"}, base_url=_BASE_URL, secret=_SECRET
        )
    )

    assert not (tmp_path / "session-1.json").exists()


def test_deliver_transcript_logs_success(monkeypatch, tmp_path: Path, caplog) -> None:
    _patch_client(monkeypatch, tmp_path, status_code=200)

    with caplog.at_level("INFO", logger="voice_agent"):
        _run(
            transcript_delivery.deliver_transcript(
                "session-log-check", {"tenantId": "t1"}, base_url=_BASE_URL, secret=_SECRET
            )
        )

    assert any(
        "transcript delivered" in record.message and "session-log-check" in record.message
        for record in caplog.records
    )


def test_deliver_transcript_keeps_outbox_file_on_http_failure(monkeypatch, tmp_path: Path) -> None:
    _patch_client(monkeypatch, tmp_path, status_code=500)

    _run(
        transcript_delivery.deliver_transcript(
            "session-2", {"tenantId": "t1"}, base_url=_BASE_URL, secret=_SECRET
        )
    )

    path = tmp_path / "session-2.json"
    assert path.exists()
    assert json.loads(path.read_text()) == {"tenantId": "t1"}


def test_deliver_transcript_keeps_outbox_file_on_network_error(monkeypatch, tmp_path: Path) -> None:
    import httpx

    _patch_client(monkeypatch, tmp_path, raises=httpx.ConnectError("connection refused"))

    _run(
        transcript_delivery.deliver_transcript(
            "session-3", {"tenantId": "t1"}, base_url=_BASE_URL, secret=_SECRET
        )
    )

    assert (tmp_path / "session-3.json").exists()


def test_flush_pending_delivers_and_removes_successful_files(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(transcript_delivery, "OUTBOX_DIR", tmp_path)
    (tmp_path / "old-session.json").write_text(json.dumps({"tenantId": "t1"}))

    client = _FakeAsyncClient(_FakeResponse(200))
    monkeypatch.setattr(transcript_delivery.httpx, "AsyncClient", lambda *a, **k: client)

    _run(transcript_delivery.flush_pending(base_url=_BASE_URL, secret=_SECRET))

    assert not (tmp_path / "old-session.json").exists()
    assert client.posted_to == f"{_BASE_URL}/internal/interview-sessions/old-session/transcript"


def test_flush_pending_is_a_noop_when_outbox_dir_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(transcript_delivery, "OUTBOX_DIR", tmp_path / "does-not-exist")
    _run(transcript_delivery.flush_pending(base_url=_BASE_URL, secret=_SECRET))
