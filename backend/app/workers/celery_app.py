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
# The lease sweeper (ADR 0037): returns work held by dead workers to pending. Needs a beat process
# (`celery -A app.workers.celery_app beat`, or a worker started with `-B` in a one-worker install).
celery_app.conf.beat_schedule = {
    "sweep-leases": {"task": "engine.sweep_leases", "schedule": settings.lease_sweep_interval_s},
    # Traffic (ADR 0032): scoring, alert checks and the retention purge for projects that are not receiving traffic now.
    "sweep-traffic": {"task": "traffic.sweep", "schedule": settings.traffic_sweep_interval_s},
}
