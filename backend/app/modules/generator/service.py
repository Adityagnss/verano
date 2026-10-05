"""
Eval Generator use cases, request side (DEVELOPMENT.md 2.3): the generator-model
suggestion, the Task Spec (drafted by one LLM call, then confirmed or edited by the user),
the cost preview shown before generating, starting generation, regenerating one category,
editing the evaluator set, and the live progress stream. The generation itself runs as a
background job (`pipeline.py`).

The Task Spec's `input_variables` always equal the prompt's required inputs, whatever the
model wrote, because cases must fill exactly those. Nothing is generated from an
unconfirmed Task Spec. The generator model may be any model of the project; a warning is
returned when it is also a model under test (a selected model), because a model can
favor its own style.
"""

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.container import Container
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.jobs import JobQueue
from app.core.progress import ProgressEvent, ProgressHub, ProgressStatus
from app.core.security import Principal, utcnow
from app.core.templates import render_system_prompt
from app.core.text import clip
from app.modules.datasets.schemas import DatasetVersionOut, ItemSource
from app.modules.datasets.service import DatasetService
from app.modules.documents.service import DocumentService
from app.modules.evaluation.schemas import EvaluatorSetUpdate, EvaluatorSetVersionOut
from app.modules.evaluation.service import EvaluatorSetService
from app.modules.gateway.dependencies import build_gateway
from app.modules.gateway.schemas import CallContext, CallPurpose, Message
from app.modules.gateway.service import GatewayService
from app.modules.generator.domain import suggest_generator
from app.modules.generator.estimate import estimate_generation
from app.modules.generator.models import TaskSpecRecord
from app.modules.generator.repository import TaskSpecRepository
from app.modules.generator.schemas import (
    TASK_SPEC_SCHEMA_VERSION,
    CaseCategory,
    GenerationEstimate,
    GenerationRequest,
    GenerationState,
    GenerationStatus,
    GeneratorModel,
    GeneratorSuggestion,
    OutputFormat,
    TaskSpec,
    TaskSpecDraftRequest,
    TaskSpecOut,
    TaskSpecProvide,
    TaskSpecStatus,
    TaskType,
)
from app.modules.projects.schemas import ProjectOut
from app.modules.prompts.service import PromptService
from app.modules.registry.service import RegistryService

PROMPTS_DIR = Path(__file__).parent / "prompts"
GENERATE_JOB = "generator.generate"
SPEC_NOT_FOUND = "This Task Spec doesn't exist in this project."
NOT_CONFIRMED = "Confirm the Task Spec (or edit and save it) before generating test cases."
WRONG_INPUTS = "input_variables must be exactly the prompt's inputs: {names}."
RUNNING = "Test cases are already being generated for this dataset version."
NOT_RUNNING = "Nothing is being generated for this dataset version."
CONFIRM_COST = (
    "This run is estimated to cost {cost} (or its price is unknown), above {limit}. "
    "Confirm the cost (accept_cost) to start."
)
NEVER_GENERATED = "Run the generator once before regenerating a category."
UNDER_TEST = "{model} is also a model under test. A model can favor its own style; a different generator is safer."
SUMMARY_CHARS = 300


def channel(version_id: uuid.UUID) -> str:
    return f"generation:{version_id}"


def spec_out(row: TaskSpecRecord, warnings: list[str] | None = None) -> TaskSpecOut:
    return TaskSpecOut(
        id=row.id,
        project_id=row.project_id,
        prompt_version_id=row.prompt_version_id,
        spec=TaskSpec.model_validate(row.spec),
        status=row.status,
        generator_credential_id=row.generator_credential_id,
        generator_model=row.generator_model,
        llm_call_id=row.llm_call_id,
        warnings=warnings or [],
        created_at=row.created_at,
        confirmed_at=row.confirmed_at,
    )


class GeneratorService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        registry: RegistryService,
        gateway: GatewayService,
        prompts: PromptService,
        datasets: DatasetService,
        documents: DocumentService,
        evaluators: EvaluatorSetService,
        jobs: JobQueue,
        progress: ProgressHub,
    ) -> None:
        self._session = session
        self._settings = settings
        self._repo = TaskSpecRepository(session)
        self._registry = registry
        self._gateway = gateway
        self._prompts = prompts
        self._datasets = datasets
        self._documents = documents
        self._evaluators = evaluators
        self._jobs = jobs
        self._progress = progress

    @classmethod
    def from_container(cls, session: AsyncSession, container: Container) -> "GeneratorService":
        settings = container.settings
        registry = RegistryService(session, container)
        return cls(
            session,
            settings,
            registry,
            build_gateway(container, registry),
            PromptService(session, registry, settings),
            DatasetService(session, settings),
            DocumentService.from_container(session, container),
            EvaluatorSetService(session),
            container.jobs,
            container.progress,
        )

    async def suggestion(self, project: ProjectOut) -> GeneratorSuggestion:
        profiles = await self._registry.profiles(project.id)
        best = suggest_generator(profiles)
        return GeneratorSuggestion(
            suggested=GeneratorModel(credential_id=best.credential_id, model=best.model_name) if best else None,
            candidates=[GeneratorModel(credential_id=p.credential_id, model=p.model_name) for p in profiles],
        )

    async def draft_spec(self, project: ProjectOut, body: TaskSpecDraftRequest) -> TaskSpecOut:
        version = await self._prompts.get_version(project.id, body.prompt_version_id)
        target = await self._registry.call_target(project.id, body.credential_id, body.model)
        draft = await self._datasets.ensure_draft(project.id)
        real = await self._datasets.items(draft.id)
        real.sort(key=lambda item: item.source is not ItemSource.GOLDEN)
        sections = await self._documents.project_sections(project.id, self._settings.generator_max_sections)
        prompt = render_system_prompt(
            PROMPTS_DIR,
            "task_spec.jinja",
            task_types=[t.value for t in TaskType],
            output_formats=[f.value for f in OutputFormat],
            input_variables=version.required_inputs,
            system_template=version.system_template,
            user_template=version.user_template,
            rows=[clip(item.inputs) for item in real[: self._settings.generator_task_spec_rows]],
            documents=[section.text[:SUMMARY_CHARS] for section in sections],
        )
        spec = await self._gateway.complete_json(
            body.model,
            [Message(role="user", content=prompt)],
            TaskSpec,
            body.credential_id,
            CallPurpose.GENERATION,
            CallContext(project_id=project.id, labels={"step": "task_spec"}),
        )
        spec.input_variables = version.required_inputs
        row = TaskSpecRecord(
            project_id=project.id,
            prompt_version_id=version.id,
            spec=spec.model_dump(mode="json"),
            schema_version=TASK_SPEC_SCHEMA_VERSION,
            status=TaskSpecStatus.DRAFT,
            generator_credential_id=body.credential_id,
            generator_model=body.model,
        )
        await self._repo.add(row)
        warnings = [UNDER_TEST.format(model=target.profile.display_name)] if target.profile.is_selected else []
        return spec_out(row, warnings)

    async def provide_spec(self, project: ProjectOut, version_id: uuid.UUID, body: TaskSpecProvide) -> TaskSpecOut:
        """A confirmed Task Spec from a spec the user wrote: no model call. The same spec and judge
        for the same prompt version give back the spec already stored, so repeating it is harmless."""
        version = await self._prompts.get_version(project.id, version_id)
        spec = TaskSpec(**body.spec.model_dump(), input_variables=version.required_inputs)
        warnings: list[str] = []
        if body.judge is not None:
            target = await self._registry.call_target(project.id, body.judge.credential_id, body.judge.model)
            if target.profile.is_selected:
                warnings.append(UNDER_TEST.format(model=target.profile.display_name))
        dumped = spec.model_dump(mode="json")
        for existing in await self._repo.confirmed_for_version(project.id, version.id):
            same_judge = (existing.generator_credential_id, existing.generator_model) == (
                (body.judge.credential_id, body.judge.model) if body.judge else (None, None)
            )
            if existing.spec == dumped and same_judge:
                return spec_out(existing, warnings)
        row = TaskSpecRecord(
            project_id=project.id,
            prompt_version_id=version.id,
            spec=dumped,
            schema_version=TASK_SPEC_SCHEMA_VERSION,
            status=TaskSpecStatus.CONFIRMED,
            confirmed_at=utcnow(),
            generator_credential_id=body.judge.credential_id if body.judge else None,
            generator_model=body.judge.model if body.judge else None,
        )
        await self._repo.add(row)
        return spec_out(row, warnings)

    async def get_spec(self, project: ProjectOut, spec_id: uuid.UUID) -> TaskSpecOut:
        return spec_out(await self._spec(project.id, spec_id))

    async def confirm_spec(self, project: ProjectOut, spec_id: uuid.UUID, spec: TaskSpec) -> TaskSpecOut:
        row = await self._spec(project.id, spec_id)
        version = await self._prompts.get_version(project.id, row.prompt_version_id)
        if sorted(spec.input_variables) != sorted(version.required_inputs):
            raise ValidationFailed(WRONG_INPUTS.format(names=", ".join(version.required_inputs)))
        row.spec = spec.model_dump(mode="json")
        row.status = TaskSpecStatus.CONFIRMED
        row.confirmed_at = utcnow()
        await self._session.flush()
        return spec_out(row)

    async def start(self, project: ProjectOut, body: GenerationRequest) -> DatasetVersionOut:
        row = await self._spec(project.id, body.task_spec_id)
        if row.status is not TaskSpecStatus.CONFIRMED:
            raise Conflict(NOT_CONFIRMED)
        draft = await self._datasets.ensure_draft(project.id)
        self._not_running(draft.generation)
        estimate = await self.estimate(project, body)
        if estimate.needs_confirmation and not body.accept_cost:
            cost = "an unknown amount" if estimate.cost is None else f"${estimate.cost:.2f}"
            raise Conflict(CONFIRM_COST.format(cost=cost, limit=f"${estimate.confirm_above:.2f}"))
        state = GenerationState(
            status=GenerationStatus.RUNNING,
            task_spec_id=row.id,
            target_size=body.target_size or self._settings.generator_default_size,
            golden_only=body.golden_only,
            budget_cap=body.budget_cap,
        )
        return await self._launch(project, draft.id, state, regenerate=None, task_spec_id=row.id)

    async def estimate(self, project: ProjectOut, body: GenerationRequest) -> GenerationEstimate:
        row = await self._spec(project.id, body.task_spec_id)
        return await estimate_generation(self._settings, self._registry, self._datasets, project.id, row, body)

    async def regenerate(self, project: ProjectOut, version_id: uuid.UUID, category: CaseCategory) -> DatasetVersionOut:
        draft = await self._datasets.draft_for_edit(project.id, version_id)
        if draft.generation is None:
            raise Conflict(NEVER_GENERATED)
        self._not_running(draft.generation)
        state = GenerationState.model_validate(draft.generation)
        state.status, state.message = GenerationStatus.RUNNING, None
        state.spent, state.cancel_requested = Decimal(0), False
        return await self._launch(project, draft.id, state, regenerate=category, task_spec_id=state.task_spec_id)

    async def cancel(self, project: ProjectOut, version_id: uuid.UUID) -> DatasetVersionOut:
        """Asks the running job to stop before its next model call; cases already written are kept."""
        version = await self._datasets.get_version(project.id, version_id)
        if not version.generation or version.generation.get("status") != GenerationStatus.RUNNING:
            raise Conflict(NOT_RUNNING)
        state = GenerationState.model_validate(version.generation)
        state.cancel_requested = True
        await self._datasets.update_version(version_id, {"generation": state.model_dump(mode="json")})
        await self._session.commit()
        return await self._datasets.get_version(project.id, version_id)

    async def edit_evaluators(
        self, project: ProjectOut, version_id: uuid.UUID, body: EvaluatorSetUpdate, principal: Principal
    ) -> EvaluatorSetVersionOut:
        draft = await self._datasets.draft_for_edit(project.id, version_id)
        if draft.evaluator_set_version_id is None:
            raise Conflict(NEVER_GENERATED)
        edited = await self._evaluators.edit(project.id, draft.evaluator_set_version_id, body, principal)
        await self._datasets.update_version(draft.id, {"evaluator_set_version_id": edited.id})
        return edited

    async def evaluators(self, project: ProjectOut, version_id: uuid.UUID) -> EvaluatorSetVersionOut:
        version = await self._datasets.get_version(project.id, version_id)
        if version.evaluator_set_version_id is None:
            raise NotFound(NEVER_GENERATED)
        return await self._evaluators.get_version(project.id, version.evaluator_set_version_id)

    async def events(self, project: ProjectOut, version_id: uuid.UUID) -> AsyncIterator[ProgressEvent | None]:
        """Reads the version before streaming starts; the stream itself only reads the progress hub."""
        version = await self._datasets.get_version(project.id, version_id)
        status = (version.generation or {}).get("status")
        if status != GenerationStatus.RUNNING and await self._progress.snapshot(channel(version_id)) is None:
            settled = ProgressStatus.FAILED if status == GenerationStatus.FAILED else ProgressStatus.SUCCEEDED
            return _once(ProgressEvent(stage="done", status=settled, message=(version.generation or {}).get("message")))
        return self._progress.stream(channel(version_id), self._settings.sse_keepalive_s)

    async def _launch(
        self,
        project: ProjectOut,
        version_id: uuid.UUID,
        state: GenerationState,
        regenerate: CaseCategory | None,
        task_spec_id: uuid.UUID,
    ) -> DatasetVersionOut:
        values = {"generation": state.model_dump(mode="json"), "task_spec_id": task_spec_id}
        await self._datasets.update_version(version_id, values)
        await self._session.commit()
        self._jobs.enqueue(
            GENERATE_JOB,
            project_id=str(project.id),
            version_id=str(version_id),
            regenerate=regenerate.value if regenerate else None,
        )
        return await self._datasets.get_version(project.id, version_id)

    @staticmethod
    def _not_running(generation: dict[str, object] | None) -> None:
        if generation and generation.get("status") == GenerationStatus.RUNNING:
            raise Conflict(RUNNING)

    async def _spec(self, project_id: uuid.UUID, spec_id: uuid.UUID) -> TaskSpecRecord:
        row = await self._repo.get(project_id, spec_id)
        if row is None:
            raise NotFound(SPEC_NOT_FOUND)
        return row


async def _once(event: ProgressEvent) -> AsyncIterator[ProgressEvent | None]:
    yield event
