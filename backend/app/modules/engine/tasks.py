"""
Engine background job: run one chunk of an experiment's calls. Idempotent: a call is
claimed before it runs, so a chunk delivered twice never repeats a call.
"""

import uuid

from app.core.container import Container
from app.core.jobs import job
from app.modules.engine.executor import ChunkExecutor


@job("engine.run_chunk", time_limit_setting="engine_chunk_timeout_s")
async def run_chunk(container: Container, experiment_id: str, run_ids: list[str]) -> None:
    async with container.database.sessions() as session:
        executor = ChunkExecutor.from_container(session, container)
        await executor.run_chunk(uuid.UUID(experiment_id), [uuid.UUID(run_id) for run_id in run_ids])
