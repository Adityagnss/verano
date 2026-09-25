"""
Celery application.

Valkey is both broker and result backend. Tasks are acknowledged only after they finish
(`acks_late`) and a worker takes one task at a time (`prefetch_multiplier=1`), so a worker
that dies mid-task hands its task back to the queue instead of losing it. Generation and
evaluation get separate queues so a slow judge never blocks generation (Phase 3/4).
"""

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery("verano", broker=settings.valkey_url, backend=settings.valkey_url, include=["app.workers.tasks"])
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_default_queue="default",
    task_queues={"default": {}, "generation": {}, "evaluation": {}},
    broker_connection_retry_on_startup=True,
)
