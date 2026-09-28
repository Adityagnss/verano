"""
Server-Sent Events responses.

Turns a stream of progress events into an SSE response: each event becomes
`event: progress` with its JSON as data, and a keepalive tick becomes an SSE comment so
idle connections survive proxies. Caddy passes the API route through unbuffered, so
events reach the browser as they happen. Clients read it with `fetch` (not
`EventSource`), because the request must carry the Authorization header.
"""

from collections.abc import AsyncIterator

from fastapi.responses import StreamingResponse

from app.core.progress import ProgressEvent

KEEPALIVE = ": keepalive\n\n"
HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


async def _encode(events: AsyncIterator[ProgressEvent | None]) -> AsyncIterator[str]:
    async for event in events:
        yield KEEPALIVE if event is None else f"event: progress\ndata: {event.model_dump_json()}\n\n"


def sse_response(events: AsyncIterator[ProgressEvent | None]) -> StreamingResponse:
    return StreamingResponse(_encode(events), media_type="text/event-stream", headers=HEADERS)
