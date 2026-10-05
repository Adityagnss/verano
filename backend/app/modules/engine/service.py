"""
Experiment use cases, request side (DEVELOPMENT.md 3.1-3.2): the cost preview, creating and
starting an experiment, cancelling it, and reading it with live progress per model.

An experiment always runs on an approved dataset version and names the exact prompt,
dataset and evaluator-set versions it used, plus a snapshot of the model profiles and
library versions; it is never changed after it starts (a new configuration is a new
experiment). Starting plans every call with a deterministic id (`plan_matrix`), stores one
pending row per call, and queues chunks of about 50 calls per provider for the workers.
Cancelling skips pending calls and keeps every finished result. Status changes go through
the state machine and are recorded as experiment events.
"""

import uuid
from dataclasses import dataclass
from importlib.metadata import version as package_version
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.container import Container
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.jobs import JobQueue
from app.core.pagination import Page, PageParams, to_page
from app.core.security import Principal, utcnow
from app.modules.datasets.models import DatasetVersion
from app.modules.datasets.schemas import ItemFilter, Split
from app.modules.datasets.service import DatasetService
from app.modules.engine.domain import chunks, ensure_transition, plan_matrix
from app.modules.engine.estimate import estimate_experiment
from app.modules.engine.fingerprint import run_configuration
from app.modules.engine.models import Experiment, ExperimentEvent
from app.modules.engine.provenance import changed_within, summarize
from app.modules.engine.repository import EngineRepository
from app.modules.engine.schemas import (
    ExperimentCreate,
    ExperimentEstimate,
    ExperimentOrigin,
    ExperimentOut,
    ExperimentStatus,
    ModelProgress,
    ModelRun,
    ModelVersions,
    ReturnedModelOut,
    RunStatus,
    SplitScope,
    TestCaseRunOut,
)
from app.modules.evaluation.service import EvaluatorSetService
from app.modules.gateway.domain import filter_params
from app.modules.generator.repository import TaskSpecRepository
from app.modules.projects.schemas import ProjectOut
from app.modules.prompts.schemas import PromptVersionOut
from app.modules.prompts.service import PromptService
from app.modules.registry.schemas import ModelProfileOut
from app.modules.registry.service import RegistryService

RUN_CHUNK_JOB = "engine.run_chunk"
EXPERIMENT_NOT_FOUND = "This experiment doesn't exist in this project."
RUN_NOT_FOUND = "This call doesn't exist in this experiment."
NO_APPROVED = "Approve your test cases (step 4) before starting an experiment."
NO_CASES = "There are no test cases in this part of the dataset."
UNKNOWN_MODELS = "Some chosen models aren't in this project any more. Refresh the Keys step."
NO_PROMPT = "Save a prompt (step 2) before starting an experiment."
NOT_FINISHED = "Wait until this experiment has finished before running it again."
NO_JUDGE_CHOSEN = (
    "Some of the checks that score the answers are judged by a model, but no judge model is chosen. "
    "Choose a judge model (Test cases step, or `judge:` in verano.yaml) before running."
)
RERUN_PREFIX = "Re-run: "
FINISHED = {ExperimentStatus.COMPLETED, ExperimentStatus.CANCELLED, ExperimentStatus.FAILED}
CANCELLED = "Cancelled by the user."
LIBRARIES = ("litellm", "deepeval")


def experiment_name(profiles: list[ModelProfileOut]) -> str:
    return " vs ".join(profile.display_name for profile in profiles)[:200]


class ExperimentService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        registry: RegistryService,
        prompts: PromptService,
        datasets: DatasetService,
        jobs: JobQueue,
    ) -> None:
        self._session = session
        self._settings = settings
        self._repo = EngineRepository(session)
        self._registry = registry
        self._prompts = prompts
        self._datasets = datasets
        self._specs = TaskSpecRepository(session)
        self._evaluators = EvaluatorSetService(session)
        self._jobs = jobs

    @classmethod
    def from_container(cls, session: AsyncSession, container: Container) -> "ExperimentService":
        settings = container.settings
        registry = RegistryService(session, container)
        prompts = PromptService(session, registry, settings)
        return cls(session, settings, registry, prompts, DatasetService(session, settings), container.jobs)

    async def estimate(self, project: ProjectOut, body: ExperimentCreate) -> ExperimentEstimate:
        plan = await self._plan_inputs(project.id, body)
        return self._estimate(plan, body)

    async def start(
        self,
        project_id: uuid.UUID,
        principal: Principal | None,
        body: ExperimentCreate,
        origin: ExperimentOrigin = ExperimentOrigin.MANUAL,
        prompt_version_id: uuid.UUID | None = None,
    ) -> ExperimentOut:
        plan = await self._plan_inputs(project_id, body, prompt_version_id)
        estimate = self._estimate(plan, body)
        experiment = Experiment(
            project_id=project_id,
            name=body.name or experiment_name(plan.profiles),
            status=ExperimentStatus.DRAFT,
            origin=origin,
            prompt_version_id=plan.prompt.id,
            dataset_version_id=plan.version.id,
            evaluator_set_version_id=plan.version.evaluator_set_version_id,
            split_scope=body.split_scope,
            config=self._config(body, plan.profiles, plan.judge),
            snapshot=self._snapshot(plan.profiles),
            estimate=estimate.model_dump(mode="json"),
            budget_cap=body.budget_cap,
            total_calls=estimate.calls,
            created_by=principal.user_id if principal else None,
        )
        await self._repo.add(experiment)
        await self._plan(experiment, plan.items, plan.profiles, body)
        await self.transition(experiment, ExperimentStatus.PLANNED)
        await self.transition(experiment, ExperimentStatus.RUNNING, values={"started_at": utcnow()})
        await self._session.commit()
        for ids in chunks(await self._repo.run_ids(experiment.id, RunStatus.PENDING), self._settings.engine_chunk_size):
            self._jobs.enqueue(RUN_CHUNK_JOB, experiment_id=str(experiment.id), run_ids=[str(i) for i in ids])
        return await self.get(project_id, experiment.id)

    async def rerun(self, project: ProjectOut, principal: Principal | None, experiment_id: uuid.UUID) -> ExperimentOut:
        """A new experiment with the same configuration: the same prompt, test cases, models,
        settings, runs and budget. Its fingerprint matches the original's."""
        row = await self._experiment(project.id, experiment_id)
        if row.status not in FINISHED:
            raise Conflict(NOT_FINISHED)
        body = ExperimentCreate(
            name=f"{RERUN_PREFIX}{row.name}"[:200],
            dataset_version_id=row.dataset_version_id,
            split_scope=row.split_scope,
            models=[
                ModelRun(model_profile_id=entry["model_profile_id"], runs=entry["runs"], params=entry["params"])
                for entry in row.config["models"]
            ],
            budget_cap=row.budget_cap,
        )
        return await self.start(project.id, principal, body, ExperimentOrigin.MANUAL, row.prompt_version_id)

    async def cancel(self, project: ProjectOut, experiment_id: uuid.UUID) -> ExperimentOut:
        experiment = await self._experiment(project.id, experiment_id)
        await self.stop(experiment, CANCELLED)
        return await self.get(project.id, experiment_id)

    async def stop(self, experiment: Experiment, reason: str) -> bool:
        """Skip every pending call and cancel; finished results are kept. False if it already ended."""
        if not await self.transition(experiment, ExperimentStatus.CANCELLED, reason, {"completed_at": utcnow()}):
            return False
        await self._repo.set_status(experiment.id, RunStatus.PENDING, RunStatus.SKIPPED)
        await self._session.commit()
        return True

    async def transition(
        self,
        experiment: Experiment,
        target: ExperimentStatus,
        reason: str | None = None,
        values: dict[str, Any] | None = None,
    ) -> bool:
        current = experiment.status
        ensure_transition(current, target)
        if not await self._repo.compare_and_set(experiment.id, current, target, values or {}):
            return False
        await self._repo.add(
            ExperimentEvent(experiment_id=experiment.id, from_status=current, to_status=target, reason=reason)
        )
        experiment.status = target
        return True

    async def list_experiments(self, project: ProjectOut, page: PageParams) -> Page[ExperimentOut]:
        rows = await self._repo.experiments(project.id, page)
        numbers = await self._repo.prompt_numbers([row.prompt_version_id for row in rows])
        return to_page([await self._out(row, numbers) for row in rows], page, lambda item: item.id)

    async def get(self, project_id: uuid.UUID, experiment_id: uuid.UUID) -> ExperimentOut:
        return await self._out(await self._experiment(project_id, experiment_id))

    async def get_run(self, project_id: uuid.UUID, experiment_id: uuid.UUID, run_id: uuid.UUID) -> TestCaseRunOut:
        await self._experiment(project_id, experiment_id)
        row = await self._repo.run(experiment_id, run_id)
        if row is None:
            raise NotFound(RUN_NOT_FOUND)
        return TestCaseRunOut.model_validate(row)

    async def experiment_row_any(self, experiment_id: uuid.UUID) -> Experiment | None:
        return await self._repo.experiment(experiment_id)

    async def experiment_row(self, project_id: uuid.UUID, experiment_id: uuid.UUID) -> Experiment:
        return await self._experiment(project_id, experiment_id)

    async def _plan_inputs(
        self, project_id: uuid.UUID, body: ExperimentCreate, prompt_version_id: uuid.UUID | None = None
    ) -> "_PlanInputs":
        version_id = body.dataset_version_id or (await self._datasets.current(project_id)).id
        version = await self._datasets.approved_version(project_id, version_id)
        split = {SplitScope.OPTIMIZE: Split.OPTIMIZE, SplitScope.HOLDOUT: Split.HOLDOUT}.get(body.split_scope)
        items = await self._datasets.items(version.id, ItemFilter(split=split))
        if not items:
            raise ValidationFailed(NO_CASES)
        wanted = [model.model_profile_id for model in body.models]
        found = {profile.id: profile for profile in await self._registry.profiles(project_id, wanted)}
        if len(found) != len(set(wanted)):
            raise ValidationFailed(UNKNOWN_MODELS)
        for model in body.models:
            filter_params(model.params, found[model.model_profile_id].parameters)
        prompt = await self._prompts.get_version(project_id, prompt_version_id or await self._latest_prompt(project_id))
        spec = await self._specs.get(project_id, version.task_spec_id) if version.task_spec_id else None
        judge, judge_profile = None, None
        if spec and spec.generator_credential_id and spec.generator_model:
            judge = {"credential_id": str(spec.generator_credential_id), "model": spec.generator_model}
            target = await self._registry.call_target(project_id, spec.generator_credential_id, spec.generator_model)
            judge_profile = target.profile
        if version.evaluator_set_version_id is None:
            raise ValidationFailed(NO_APPROVED)
        evaluators = await self._evaluators.get_version(project_id, version.evaluator_set_version_id)
        judge_metrics = sum(1 for e in evaluators.evaluators if e.config.get("kind") == "deepeval")
        if judge_metrics and judge_profile is None:
            raise ValidationFailed(NO_JUDGE_CHOSEN)
        return _PlanInputs(
            version=version,
            items=[(item.id, item.inputs) for item in items],
            profiles=[found[m] for m in wanted],
            prompt=prompt,
            judge=judge,
            judge_profile=judge_profile,
            judge_metrics=judge_metrics,
        )

    def _estimate(self, plan: "_PlanInputs", body: ExperimentCreate) -> ExperimentEstimate:
        return estimate_experiment(
            self._settings, plan.prompt, plan.items, plan.profiles, body, plan.judge_profile, plan.judge_metrics
        )

    async def _latest_prompt(self, project_id: uuid.UUID) -> uuid.UUID:
        latest = await self._prompts.latest_version_id(project_id)
        if latest is None:
            raise ValidationFailed(NO_PROMPT)
        return latest

    async def _plan(
        self,
        experiment: Experiment,
        items: list[tuple[uuid.UUID, dict[str, Any]]],
        profiles: list[ModelProfileOut],
        body: ExperimentCreate,
    ) -> None:
        by_id = {profile.id: profile for profile in profiles}
        planned = plan_matrix(
            experiment.id,
            [item_id for item_id, _ in items],
            [(m.model_profile_id, m.runs, m.params) for m in body.models],
        )
        await self._repo.insert_runs(
            [
                {
                    "experiment_id": experiment.id,
                    "id": call.id,
                    "dataset_item_id": call.dataset_item_id,
                    "prompt_version_id": experiment.prompt_version_id,
                    "model_profile_id": call.model_profile_id,
                    "credential_id": by_id[call.model_profile_id].credential_id,
                    "provider": by_id[call.model_profile_id].provider,
                    "model": by_id[call.model_profile_id].model_name,
                    "param_set_key": call.param_set_key,
                    "params": call.params,
                    "run_number": call.run_number,
                    "status": RunStatus.PENDING,
                }
                for call in planned
            ]
        )

    @staticmethod
    def _config(
        body: ExperimentCreate, profiles: list[ModelProfileOut], judge: dict[str, Any] | None
    ) -> dict[str, Any]:
        by_id = {profile.id: profile for profile in profiles}
        return {
            "models": [
                {
                    "model_profile_id": str(model.model_profile_id),
                    "display_name": by_id[model.model_profile_id].display_name,
                    "runs": model.runs,
                    "params": model.params,
                    "ignored_params": sorted(set(model.params) - set(by_id[model.model_profile_id].parameters)),
                }
                for model in body.models
            ],
            "judge": judge,
        }

    @staticmethod
    def _snapshot(profiles: list[ModelProfileOut]) -> dict[str, Any]:
        libraries: dict[str, str | None] = {}
        for name in LIBRARIES:
            try:
                libraries[name] = package_version(name)
            except Exception:
                libraries[name] = None
        return {"profiles": [p.model_dump(mode="json") for p in profiles], "libraries": libraries}

    async def _experiment(self, project_id: uuid.UUID, experiment_id: uuid.UUID) -> Experiment:
        row = await self._repo.experiment(experiment_id, project_id)
        if row is None:
            raise NotFound(EXPERIMENT_NOT_FOUND)
        return row

    async def _model_versions(self, row: Experiment) -> list[ModelVersions]:
        found = summarize(await self._repo.returned_models(row.id))
        return [
            ModelVersions(
                model_profile_id=entry["model_profile_id"],
                display_name=entry.get("display_name", ""),
                returned=[
                    ReturnedModelOut(id=r.id, calls=r.calls)
                    for r in found.get(uuid.UUID(str(entry["model_profile_id"])), [])
                ],
                changed=changed_within(found.get(uuid.UUID(str(entry["model_profile_id"])), [])),
            )
            for entry in row.config["models"]
        ]

    async def _out(self, row: Experiment, numbers: dict[uuid.UUID, int] | None = None) -> ExperimentOut:
        numbers = numbers or await self._repo.prompt_numbers([row.prompt_version_id])
        progress: dict[uuid.UUID, ModelProgress] = {}
        for model_id, model, status, count, cost in await self._repo.progress(row.id):
            entry = progress.setdefault(model_id, ModelProgress(model_profile_id=model_id, model=model))
            entry.total += count
            entry.cost += cost or 0
            if status in (RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.SKIPPED):
                setattr(entry, status.value, getattr(entry, status.value) + count)
        return ExperimentOut(
            **{name: getattr(row, name) for name in ExperimentOut.model_fields if hasattr(row, name)},
            stop_reason=await self._repo.last_reason(row.id),
            progress=list(progress.values()),
            configuration=run_configuration(row, numbers.get(row.prompt_version_id)),
            model_versions=await self._model_versions(row),
        )


@dataclass(frozen=True)
class _PlanInputs:
    version: DatasetVersion
    items: list[tuple[uuid.UUID, dict[str, Any]]]
    profiles: list[ModelProfileOut]
    prompt: PromptVersionOut
    judge: dict[str, Any] | None
    judge_profile: ModelProfileOut | None
    judge_metrics: int
