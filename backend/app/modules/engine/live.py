"""
Live progress of one experiment over Server-Sent Events (ADR 0037).

The server watches the run (one small read per tick, however many people have the page open is one read per
connection) and sends an event only when the numbers or state changed; the browser reacts to an event instead of
asking every second. Ticks come fast while things change and slow down when nothing does. The stream ends when the
run is completed, cancelled or failed. Sessions are opened per tick because the request's own session is closed once
the response starts.
"""

import asyncio
import time
import uuid
from collections.abc import AsyncIterator

from app.core.container import Container
from app.core.errors import AppError
from app.core.progress import ProgressEvent, ProgressStatus
from app.modules.engine.schemas import ExperimentOut, ExperimentStatus
from app.modules.engine.service import ExperimentService

ENDED = {ExperimentStatus.COMPLETED, ExperimentStatus.CANCELLED, ExperimentStatus.FAILED}


def to_event(out: ExperimentOut) -> ProgressEvent:
    done = sum(p.succeeded + p.failed + p.skipped for p in out.progress)
    total = sum(p.total for p in out.progress)
    scoring = out.scoring
    message: str | None
    if scoring is not None:
        message = f"Scoring answers: {scoring.done} of {scoring.total}."
    elif out.eta_seconds is not None:
        message = f"About {out.eta_seconds} seconds left."
    else:
        message = out.stop_reason
    status = ProgressStatus.RUNNING
    if out.status is ExperimentStatus.COMPLETED:
        status = ProgressStatus.SUCCEEDED
    elif out.status in (ExperimentStatus.CANCELLED, ExperimentStatus.FAILED):
        status = ProgressStatus.FAILED
    return ProgressEvent(stage=out.status.value, status=status, processed=done, total=total, message=message)


async def stream_experiment(
    container: Container, project_id: uuid.UUID, experiment_id: uuid.UUID
) -> AsyncIterator[ProgressEvent | None]:
    settings = container.settings
    last: ProgressEvent | None = None
    quiet_since = time.monotonic()
    wait = settings.sse_poll_s
    while True:
        try:
            async with container.database.sessions() as session:
                out = await ExperimentService.from_container(session, container).get(project_id, experiment_id)
        except AppError:
            return
        event = to_event(out)
        if event != last:
            last, quiet_since, wait = event, time.monotonic(), settings.sse_poll_s
            yield event
        else:
            wait = settings.sse_idle_poll_s
            if time.monotonic() - quiet_since >= settings.sse_keepalive_s:
                quiet_since = time.monotonic()
                yield None
        if out.status in ENDED:
            return
        await asyncio.sleep(wait)
