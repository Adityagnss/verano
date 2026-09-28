"""
The Eval Generator job (DEVELOPMENT.md 2.3 Steps B-E) for one draft dataset version.

B  Real rows (golden set, input files) are already in the draft. Generated cases fill only
   what is missing per category (`plan_targets`), one category per batch call, with real
   rows as style examples and, when documents exist, grounded in numbered sections (the
   cited section becomes the case's `context`).
C  Every new case is validated (all required inputs, non-blank) and dropped if its
   embedding is too similar to any case kept so far; real rows are never dropped. Short
   categories are topped up for a few rounds. For classification, a label no case covers
   gets cases written for it.
D  Input-file and generated drafts without an answer get a drafted expected output (one
   correct answer) or rubric (many acceptable answers). Only draft rows are written to, so
   golden answers are never overwritten.
E  The evaluator set is selected from the Task Spec and linked to the version.
"Use only my golden set" skips B-D: no LLM call is made.
The job is idempotent: a full run first removes earlier generated cases, a category
regeneration removes that category's. Progress streams on the version's channel; a
failure is recorded on the version with a clear message.
"""

import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.container import Container
from app.core.datafiles import load_yaml
from app.core.errors import AppError, ValidationFailed
from app.core.progress import ProgressEvent, ProgressHub, ProgressStatus
from app.modules.datasets.service import DatasetService
from app.modules.documents.service import DocumentService
from app.modules.evaluation.schemas import EvaluatorConfigIn
from app.modules.evaluation.service import EvaluatorSetService
from app.modules.gateway.dependencies import build_gateway
from app.modules.gateway.service import GatewayService
from app.modules.generator.domain import (
    EvaluatorCatalog,
    GenerationCatalog,
    select_evaluators,
)
from app.modules.generator.plugins.embedders import Embedder, build_embedder
from app.modules.generator.repository import TaskSpecRepository
from app.modules.generator.run import GenerationRun, RunDeps
from app.modules.generator.schemas import (
    CaseCategory,
    GenerationState,
    GenerationStatus,
    TaskSpec,
)
from app.modules.generator.service import channel
from app.modules.prompts.service import PromptService
from app.modules.registry.service import RegistryService

CONFIG = Path(__file__).parent / "config"
EVALUATOR_CATALOG = Path(__file__).parents[1] / "evaluation" / "config" / "catalog.yaml"
SPEC_GONE = "The Task Spec for this generation was deleted. Draft and confirm a new one."
MODEL_GONE = "The generator model's key was removed. Draft the Task Spec again with an available model."
EVALUATORS_REASON = "Selected automatically from the Task Spec ({task_type})."


class GenerationPipeline:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        gateway: GatewayService,
        prompts: PromptService,
        datasets: DatasetService,
        documents: DocumentService,
        evaluators: EvaluatorSetService,
        progress: ProgressHub,
        embedder: Embedder,
    ) -> None:
        self._session = session
        self._settings = settings
        self._gateway = gateway
        self._prompts = prompts
        self._datasets = datasets
        self._documents = documents
        self._evaluators = evaluators
        self._progress = progress
        self._embedder = embedder
        self._specs = TaskSpecRepository(session)
        self._categories = load_yaml(CONFIG / "generation.yaml", GenerationCatalog)
        self._evaluator_catalog = load_yaml(EVALUATOR_CATALOG, EvaluatorCatalog)

    @classmethod
    def from_container(cls, session: AsyncSession, container: Container) -> "GenerationPipeline":
        settings = container.settings
        registry = RegistryService(session, container)
        return cls(
            session,
            settings,
            build_gateway(container, registry),
            PromptService(session, registry, settings),
            DatasetService(session, settings),
            DocumentService.from_container(session, container),
            EvaluatorSetService(session),
            container.progress,
            build_embedder(settings),
        )

    async def run(self, project_id: uuid.UUID, version_id: uuid.UUID, regenerate: CaseCategory | None) -> None:
        version = await self._datasets.get_version(project_id, version_id)
        state = GenerationState.model_validate(version.generation)
        try:
            await self._run(project_id, version_id, state, regenerate)
        except AppError as exc:
            await self.fail(project_id, version_id, exc.message)
            return
        state.status = GenerationStatus.SUCCEEDED
        await self._save_state(version_id, state)
        await self._publish(version_id, "done", ProgressStatus.SUCCEEDED, message="Test cases are ready for review.")

    async def fail(self, project_id: uuid.UUID, version_id: uuid.UUID, message: str) -> None:
        await self._session.rollback()
        version = await self._datasets.get_version(project_id, version_id)
        if version.generation is not None:
            state = GenerationState.model_validate(version.generation)
            state.status, state.message = GenerationStatus.FAILED, message
            await self._save_state(version_id, state)
        await self._publish(version_id, "failed", ProgressStatus.FAILED, message=message)

    async def _run(
        self, project_id: uuid.UUID, version_id: uuid.UUID, state: GenerationState, regenerate: CaseCategory | None
    ) -> None:
        record = await self._specs.get(project_id, state.task_spec_id)
        if record is None:
            raise ValidationFailed(SPEC_GONE)
        if not state.golden_only and (record.generator_credential_id is None or record.generator_model is None):
            raise ValidationFailed(MODEL_GONE)
        spec = TaskSpec.model_validate(record.spec)
        deps = RunDeps(
            self._settings,
            self._session,
            self._datasets,
            self._embedder,
            self._categories,
            self._gateway,
            self._publish,
        )
        run = GenerationRun(deps, project_id, version_id, state, spec, record)
        if not state.golden_only:
            prompt = await self._prompts.get_version(project_id, record.prompt_version_id)
            sections = await self._documents.project_sections(project_id, self._settings.generator_max_sections)
            run.prompt, run.sections = prompt, [section.text for section in sections]
            await self._datasets.delete_generated(version_id, regenerate.value if regenerate else None)
            await self._session.commit()
            state.embedding_model = self._embedder.name
            await run.generate(regenerate)
            await run.draft_answers()
            if regenerate is None:
                await run.balance_labels()
        if regenerate is None:
            await self._select_evaluators(project_id, version_id, spec)
        state.counts = await run.counts()

    async def _select_evaluators(self, project_id: uuid.UUID, version_id: uuid.UUID, spec: TaskSpec) -> None:
        choices = select_evaluators(spec, self._evaluator_catalog)
        configs = [
            EvaluatorConfigIn(
                evaluator_name=c.name,
                evaluator_version=c.version,
                config=c.config,
                threshold=c.threshold,
                weight=c.weight,
                required=c.required,
            )
            for c in choices
        ]
        reason = EVALUATORS_REASON.format(task_type=spec.task_type.value)
        created = await self._evaluators.create_version(project_id, configs, reason)
        await self._datasets.update_version(version_id, {"evaluator_set_version_id": created.id})
        await self._session.commit()

    async def _save_state(self, version_id: uuid.UUID, state: GenerationState) -> None:
        await self._datasets.update_version(version_id, {"generation": state.model_dump(mode="json")})
        await self._session.commit()

    async def _publish(
        self,
        version_id: uuid.UUID,
        stage: str,
        status: ProgressStatus = ProgressStatus.RUNNING,
        processed: int = 0,
        total: int | None = None,
        message: str | None = None,
    ) -> None:
        event = ProgressEvent(stage=stage, status=status, processed=processed, total=total, message=message)
        await self._progress.publish(channel(version_id), event)
