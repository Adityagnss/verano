"""
Task entry points. Each task is a thin wrapper that builds a container and calls a module
service; no business logic lives here. `ping` lets health checks confirm a worker is
consuming from the queue.
"""

from app.workers.celery_app import celery_app


@celery_app.task(name="system.ping")
def ping() -> str:
    return "pong"
