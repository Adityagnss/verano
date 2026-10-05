"""
The experiment executor (DEVELOPMENT.md 3.3-3.4): runs one chunk of calls.

Calls run concurrently with asyncio. Model targets are resolved once per chunk and the
read transaction is committed before any call, so no database transaction stays open
while a model is thinking; the chunk's session is only used under a lock, and every use
ends with a commit. At most `engine_provider_concurrency` calls run per provider in a
chunk (the gateway's rate limiter also paces each provider across all workers).
Each call is claimed by moving its row from pending to running, so a chunk delivered twice
never repeats a call; its result is saved as soon as it arrives. Transient provider errors
are retried by the gateway, so only that call is retried; a call that still fails is
recorded as failed with its error type and message. After each call the spend is checked
against the budget cap, and the experiment stops (pending calls skipped, results kept)
when it is reached. When the last open call finishes, the experiment moves on to scoring.
Every call records the rendered prompts, exact parameters sent, raw and parsed output,
tokens, cost, latency, attempts, the gateway's call id and its trace ids.
"""

import asyncio
import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.container import Container
from app.core.errors import AppError
from app.core.jobs import JobQueue
from app.core.security import utcnow
from app.modules.datasets.service import DatasetService
from app.modules.engine.domain import parse_output
from app.modules.engine.models import Experiment, TestCaseRun
from app.modules.engine.repository import EngineRepository
from app.modules.engine.schemas import ExperimentStatus, RunStatus
from app.modules.engine.service import ExperimentService
from app.modules.gateway.dependencies import build_gateway
from app.modules.gateway.schemas import CallContext, CallPurpose, Message
from app.modules.gateway.service import GatewayService
from app.modules.prompts.domain import render
from app.modules.prompts.schemas import PromptVersionOut
from app.modules.prompts.service import PromptService
from app.modules.registry.schemas import CallTarget
from app.modules.registry.service import RegistryService

SCORE_JOB = "evaluation.score_experiment"
BUDGET_REACHED = "Budget cap of ${cap} reached; the remaining calls were skipped."
INTERNAL = "internal_error"


class ChunkExecutor:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        gateway: GatewayService,
        registry: RegistryService,
        prompts: PromptService,
        datasets: DatasetService,
        experiments: ExperimentService,
        jobs: JobQueue,
    ) -> None:
        self._session = session
        self._settings = settings
        self._repo = EngineRepository(session)
        self._gateway = gateway
        self._registry = registry
        self._prompts = prompts
        self._datasets = datasets
        self._experiments = experiments
        self._jobs = jobs
        self._lock = asyncio.Lock()

    @classmethod
    def from_container(cls, session: AsyncSession, container: Container) -> "ChunkExecutor":
        registry = RegistryService(session, container)
        prompts = PromptService(session, registry, container.settings)
        return cls(
            session,
            container.settings,
            build_gateway(container, registry),
            registry,
            prompts,
            DatasetService(session, container.settings),
            ExperimentService.from_container(session, container),
            container.jobs,
        )

    async def run_chunk(self, experiment_id: uuid.UUID, run_ids: list[uuid.UUID]) -> None:
        experiment = await self._repo.experiment(experiment_id)
        if experiment is None or experiment.status is not ExperimentStatus.RUNNING:
            return
        rows = [row for row in await self._repo.runs(experiment_id, run_ids) if row.status is RunStatus.PENDING]
        prompt = await self._prompts.get_version(experiment.project_id, experiment.prompt_version_id)
        items = await self._datasets.items(experiment.dataset_version_id, ids=[row.dataset_item_id for row in rows])
        inputs = {item.id: item.inputs for item in items}
        targets = {
            key: await self._registry.call_target(experiment.project_id, key[0], key[1])
            for key in {(row.credential_id or uuid.UUID(int=0), row.model) for row in rows}
        }
        await self._session.commit()
        limits: dict[str, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(self._settings.engine_provider_concurrency)
        )

        async def one(row: TestCaseRun) -> None:
            async with limits[row.provider]:
                target = targets[(row.credential_id or uuid.UUID(int=0), row.model)]
                await self._call(experiment, prompt, row, inputs[row.dataset_item_id], target)

        await asyncio.gather(*(one(row) for row in rows))
        await self._finish_if_done(experiment)

    async def _call(
        self,
        experiment: Experiment,
        prompt: PromptVersionOut,
        row: TestCaseRun,
        inputs: dict[str, Any],
        target: CallTarget,
    ) -> None:
        async with self._lock:
            if experiment.status is not ExperimentStatus.RUNNING:
                return
            if not await self._repo.claim(experiment.id, row.id, utcnow()):
                return
            await self._session.commit()
        messages = render(prompt.system_template, prompt.user_template, inputs)
        values = self._rendered(messages)
        try:
            result = await self._gateway.complete_target(
                target,
                messages,
                row.params,
                CallPurpose.TEST_RUN,
                CallContext(project_id=experiment.project_id, experiment_id=experiment.id, test_case_run_id=row.id),
            )
            values |= {
                "status": RunStatus.SUCCEEDED,
                "raw_output": result.text,
                "parsed_output": parse_output(result.text),
                "finish_reason": result.finish_reason,
                "response_model": result.response_model,
                "params": result.params,
                "attempts": result.attempts,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "cost": result.cost,
                "latency_ms": result.latency_ms,
                "llm_call_id": result.call_id,
                "trace_id": result.trace_id,
                "span_id": result.span_id,
            }
        except AppError as error:
            call_id = error.details.get("llm_call_id")
            values |= {
                "status": RunStatus.FAILED,
                "error_type": error.code,
                "error_message": error.message,
                "attempts": 1,
                "llm_call_id": uuid.UUID(call_id) if call_id else None,
            }
        async with self._lock:
            await self._repo.update_run(experiment.id, row.id, values | {"completed_at": utcnow()})
            await self._session.commit()
            await self._check_budget(experiment)
            await self._session.commit()

    @staticmethod
    def _rendered(messages: list[Message]) -> dict[str, Any]:
        system = next((m.content for m in messages if m.role == "system"), None)
        user = next((m.content for m in messages if m.role == "user"), None)
        return {"rendered_system_prompt": system, "rendered_user_prompt": user}

    async def _check_budget(self, experiment: Experiment) -> None:
        if experiment.budget_cap is None or experiment.status is not ExperimentStatus.RUNNING:
            return
        reached = await self._repo.spent(experiment.id) >= experiment.budget_cap
        if reached and await self._experiments.stop(experiment, BUDGET_REACHED.format(cap=experiment.budget_cap)):
            self._jobs.enqueue(SCORE_JOB, experiment_id=str(experiment.id))

    async def _finish_if_done(self, experiment: Experiment) -> None:
        fresh = await self._repo.experiment(experiment.id)
        if fresh is None or fresh.status is not ExperimentStatus.RUNNING or await self._repo.open_count(fresh.id):
            return
        if await self._experiments.transition(fresh, ExperimentStatus.EVALUATING):
            await self._session.commit()
            self._jobs.enqueue(SCORE_JOB, experiment_id=str(fresh.id))
