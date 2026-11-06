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
from app.core.text import bound
from app.modules.apps.caller import AppCaller, PreparedApp
from app.modules.apps.models import AppCall
from app.modules.apps.repository import AppRepository
from app.modules.apps.schemas import AppMode
from app.modules.apps.simulator import SimulatedUser
from app.modules.datasets.service import DatasetService
from app.modules.engine.domain import parse_output
from app.modules.engine.models import Experiment, TestCaseRun
from app.modules.engine.repository import EngineRepository
from app.modules.engine.schemas import ExperimentStatus, RunStatus
from app.modules.engine.service import ExperimentService
from app.modules.gateway.dependencies import build_gateway
from app.modules.gateway.schemas import CallContext, CallPurpose, Message
from app.modules.gateway.service import GatewayService
from app.modules.gateway.spend import SpendGuard
from app.modules.prompts.domain import render
from app.modules.prompts.schemas import PromptVersionOut
from app.modules.prompts.service import PromptService
from app.modules.registry.schemas import CallTarget
from app.modules.registry.service import RegistryService

SCORE_JOB = "evaluation.score_experiment"
BUDGET_REACHED = "Budget cap of ${cap} reached; the remaining calls were skipped."
INTERNAL = "internal_error"
APP_PROVIDER = "app"
NO_SIMULATOR = "This app holds conversations, so a judge model must be chosen to play the user."


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
        apps: AppCaller | None = None,
        spend: SpendGuard | None = None,
    ) -> None:
        self._spend = spend
        self._session = session
        self._apps = apps
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
            AppCaller(session, container),
            SpendGuard(container.database.sessions),
        )

    async def run_chunk(self, experiment_id: uuid.UUID, run_ids: list[uuid.UUID]) -> None:
        experiment = await self._repo.experiment(experiment_id)
        if experiment is None or experiment.status is not ExperimentStatus.RUNNING:
            return
        rows = [row for row in await self._repo.runs(experiment_id, run_ids) if row.status is RunStatus.PENDING]
        if await self._stop_for_spend_limit(experiment):
            return
        prompt = await self._prompts.get_version(experiment.project_id, experiment.prompt_version_id)
        items = await self._datasets.items(experiment.dataset_version_id, ids=[row.dataset_item_id for row in rows])
        inputs = {item.id: item.inputs for item in items}
        model_rows = [row for row in rows if row.provider != APP_PROVIDER]
        app_rows = [row for row in rows if row.provider == APP_PROVIDER]
        targets = {
            key: await self._registry.call_target(experiment.project_id, key[0], key[1])
            for key in {(row.credential_id or uuid.UUID(int=0), row.model) for row in model_rows}
        }
        apps = (
            await self._apps.prepare({row.credential_id for row in app_rows if row.credential_id})
            if self._apps and app_rows
            else {}
        )
        judge = (
            await self._judge_target(experiment) if any(a.mode is AppMode.CONVERSATION for a in apps.values()) else None
        )
        await self._session.commit()
        limits: dict[str, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(self._settings.engine_provider_concurrency)
        )
        app_limits = {cid: asyncio.Semaphore(app.concurrency) for cid, app in apps.items()}

        async def one(row: TestCaseRun) -> None:
            if row.provider == APP_PROVIDER:
                prepared = apps.get(row.credential_id or uuid.UUID(int=0))
                if prepared is None:
                    await self._fail_app(experiment, row, "This app no longer exists.")
                    return
                async with app_limits[row.credential_id or uuid.UUID(int=0)]:
                    await self._call_app(experiment, row, inputs[row.dataset_item_id], prepared, judge)
                return
            async with limits[row.provider]:
                target = targets[(row.credential_id or uuid.UUID(int=0), row.model)]
                await self._call(experiment, prompt, row, inputs[row.dataset_item_id], target)

        await asyncio.gather(*(one(row) for row in rows))
        await self._finish_if_done(experiment)

    async def _judge_target(self, experiment: Experiment) -> CallTarget | None:
        """The model that plays the user in a conversation: the experiment's judge."""
        choice = experiment.config.get("judge")
        if not choice:
            return None
        return await self._registry.call_target(
            experiment.project_id, uuid.UUID(choice["credential_id"]), choice["model"]
        )

    async def _claim(self, experiment: Experiment, row: TestCaseRun) -> bool:
        async with self._lock:
            if experiment.status is not ExperimentStatus.RUNNING:
                return False
            if not await self._repo.claim(experiment.id, row.id, utcnow()):
                return False
            await self._session.commit()
            return True

    async def _fail_app(self, experiment: Experiment, row: TestCaseRun, why: str) -> None:
        if not await self._claim(experiment, row):
            return
        values = {"status": RunStatus.FAILED, "error_type": "app_error", "error_message": why, "attempts": 1}
        await self._save(experiment, row, values, [], None)

    async def _call_app(
        self,
        experiment: Experiment,
        row: TestCaseRun,
        inputs: dict[str, Any],
        app: PreparedApp,
        judge: CallTarget | None,
    ) -> None:
        """One test case sent to the user's app (or a whole conversation with it). The app's own model calls are
        not ours: its cost is stored only when it reports one, and a simulated user's calls are costed here."""
        if not await self._claim(experiment, row):
            return
        user: SimulatedUser | None = None
        if app.mode is AppMode.CONVERSATION:
            if judge is None:
                await self._save(
                    experiment,
                    row,
                    {"status": RunStatus.FAILED, "error_type": "app_error", "error_message": NO_SIMULATOR},
                    [],
                    None,
                )
                return
            context = CallContext(
                project_id=experiment.project_id, experiment_id=experiment.id, test_case_run_id=row.id
            )
            user = SimulatedUser(self._gateway, judge, context, inputs)
        try:
            outcome = await self._apps.run(app, inputs, user.as_simulator() if user else None) if self._apps else None
        except AppError as error:
            failure: dict[str, Any] = {
                "status": RunStatus.FAILED,
                "error_type": error.code,
                "error_message": error.message,
            }
            await self._save(experiment, row, failure, [], None)
            return
        if outcome is None:
            return
        values: dict[str, Any] = dict(outcome.values)
        if user is not None and user.cost:
            values["cost"] = (values.get("cost") or 0) + user.cost
        await self._save(experiment, row, values, outcome.calls, app.target_id)

    async def _save(
        self,
        experiment: Experiment,
        row: TestCaseRun,
        values: dict[str, Any],
        calls: list[dict[str, Any]],
        target_id: uuid.UUID | None,
    ) -> None:
        async with self._lock:
            await self._repo.update_run(experiment.id, row.id, values | {"completed_at": utcnow()})
            if calls and target_id is not None:
                await AppRepository(self._session).add_calls(
                    [
                        AppCall(experiment_id=experiment.id, test_case_run_id=row.id, app_target_id=target_id, **call)
                        for call in calls
                    ]
                )
            await self._session.commit()
            await self._check_budget(experiment)
            await self._session.commit()

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
            text, cut = bound(result.text, self._settings.stored_answer_max_chars)
            values |= {
                "status": RunStatus.SUCCEEDED,
                "raw_output": text,
                "output_truncated": cut,
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
        if experiment.status is not ExperimentStatus.RUNNING:
            return
        if experiment.budget_cap is not None:
            reached = await self._repo.spent(experiment.id) >= experiment.budget_cap
            if reached and await self._experiments.stop(experiment, BUDGET_REACHED.format(cap=experiment.budget_cap)):
                self._jobs.enqueue(SCORE_JOB, experiment_id=str(experiment.id))
                return
        await self._stop_for_spend_limit(experiment)

    async def _stop_for_spend_limit(self, experiment: Experiment) -> bool:
        """Stop the run, keeping its results, when the workspace's monthly limit is reached; the calls already
        in flight finish, the rest are skipped, and the run says why."""
        if self._spend is None or experiment.status is not ExperimentStatus.RUNNING:
            return False
        why = await self._spend.reason(experiment.project_id)
        if why and await self._experiments.stop(experiment, why):
            self._jobs.enqueue(SCORE_JOB, experiment_id=str(experiment.id))
            return True
        return False

    async def _finish_if_done(self, experiment: Experiment) -> None:
        fresh = await self._repo.experiment(experiment.id)
        if fresh is None or fresh.status is not ExperimentStatus.RUNNING or await self._repo.open_count(fresh.id):
            return
        if await self._experiments.transition(fresh, ExperimentStatus.EVALUATING):
            await self._session.commit()
            self._jobs.enqueue(SCORE_JOB, experiment_id=str(fresh.id))
