"""Live events: publish() from any thread, GET /api/events streams them (SSE)."""

import asyncio
import contextlib
import json

from fastapi import APIRouter
from sse_starlette import EventSourceResponse

from api.core import HEARTBEAT_S

router = APIRouter()


_subscribers: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = set()


def publish(event: str, data: dict) -> None:
    """Send to every SSE client. Safe from any thread."""
    msg = {"event": event, "data": json.dumps(data)}
    for loop, q in list(_subscribers):
        with contextlib.suppress(RuntimeError):  # that client's loop is gone
            loop.call_soon_threadsafe(q.put_nowait, msg)


@router.get("/api/events")
async def events():
    sub = (asyncio.get_running_loop(), asyncio.Queue())

    async def stream():
        _subscribers.add(sub)
        try:
            yield {"event": "hello", "data": "{}"}
            while True:
                yield await sub[1].get()
        finally:
            _subscribers.discard(sub)

    return EventSourceResponse(stream(), ping=HEARTBEAT_S)
