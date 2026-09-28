"""
The production `JobQueue`: sends a registered job to Celery by name, on the job's queue.
Used by the API and by workers (a job may enqueue a follow-up job).
"""

from typing import Any

from app.core.jobs import JOBS
from app.workers.celery_app import celery_app


class CeleryJobQueue:
    def enqueue(self, name: str, **kwargs: Any) -> None:
        celery_app.send_task(name, kwargs=kwargs, queue=JOBS[name].queue)
