"""
Push-based delivery for the dev metrics dashboard (see metrics_dashboard.py),
replacing "poll every 1.5s regardless of activity" with a single WebSocket
connection per open browser tab. The background watcher below still reads
the same local files metrics_log.py writes (no change to how the worker
process gets data to the dashboard process) — what changes is that a
browser tab now sees exactly one persistent connection with zero traffic
until something actually happens, instead of a GET request firing forever
in the background even when no interview is running.

The watcher does nothing at all (skips its file check entirely) whenever no
client is connected — this is the actual fix for "why is it still calling
the API when nothing is running": previously polling had no way to know
"nothing is running," it just fired on a timer regardless. Now there is
nothing for it to fire.
"""

import asyncio
import contextlib

from fastapi import WebSocket, WebSocketDisconnect

from ..model_gateway.metrics_log import (
    latest_agent_metric_ts,
    latest_metric_ts,
    read_recent,
    read_recent_agent_metrics,
    read_transcript_snapshot,
    slim_llm_record,
)

_POLL_INTERVAL_S = 1.0


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    def add(self, ws: WebSocket) -> None:
        self._connections.add(ws)

    def remove(self, ws: WebSocket) -> None:
        self._connections.discard(ws)

    def has_connections(self) -> bool:
        return bool(self._connections)

    async def broadcast(self, message: dict) -> None:
        dead = []
        for ws in self._connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.discard(ws)


manager = ConnectionManager()
_watcher_task: asyncio.Task | None = None


async def _watch_and_broadcast() -> None:
    last_llm_ts = latest_metric_ts()
    last_agent_ts = latest_agent_metric_ts()
    last_transcript_updated_at: float | None = None

    while True:
        await asyncio.sleep(_POLL_INTERVAL_S)
        if not manager.has_connections():
            continue  # nobody watching — do zero work, not even a file read

        new_llm = read_recent(after_ts=last_llm_ts)
        for record in new_llm:
            await manager.broadcast({"type": "llm", "record": slim_llm_record(record)})
        if new_llm:
            last_llm_ts = new_llm[-1]["ts"]

        new_agent = read_recent_agent_metrics(after_ts=last_agent_ts)
        for record in new_agent:
            await manager.broadcast({"type": "agent", "record": record})
        if new_agent:
            last_agent_ts = new_agent[-1]["ts"]

        snapshot = read_transcript_snapshot()
        if snapshot and snapshot.get("updated_at") != last_transcript_updated_at:
            last_transcript_updated_at = snapshot.get("updated_at")
            await manager.broadcast({"type": "transcript", "snapshot": snapshot})


def _ensure_watcher_started() -> None:
    global _watcher_task
    if _watcher_task is None or _watcher_task.done():
        _watcher_task = asyncio.create_task(_watch_and_broadcast())


async def metrics_websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    _ensure_watcher_started()
    manager.add(ws)
    try:
        while True:
            # This endpoint is push-only; block here just to detect disconnect.
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.remove(ws)
        with contextlib.suppress(Exception):
            await ws.close()
