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

import asyncio
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.container import Container
from app.core.datafiles import load_yaml
from app.core.errors import AppError, ValidationFailed
from app.core.progress import ProgressEvent, ProgressHub, ProgressStatus
from app.core.templates import render_system_prompt
from app.modules.datasets.domain import is_blank
from app.modules.datasets.models import DatasetItem
from app.modules.datasets.schemas import ItemFilter, ItemSource, ReviewStatus
from app.modules.datasets.service import DatasetService
from app.modules.documents.service import DocumentService
from app.modules.evaluation.schemas import EvaluatorConfigIn
from app.modules.evaluation.service import EvaluatorSetService
from app.modules.gateway.dependencies import build_gateway
from app.modules.gateway.schemas import CallContext, CallPurpose, Message
from app.modules.gateway.service import GatewayService
from app.modules.generator.domain import (
    EvaluatorCatalog,
    GenerationCatalog,
    answer_label,
    case_text,
    is_single_answer,
    missing_labels,
    near_duplicates,
    plan_targets,
    select_evaluators,
)
from app.modules.generator.models import TaskSpecRecord
from app.modules.generator.plugins.embedders import Embedder, build_embedder
from app.modules.generator.repository import TaskSpecRepository
from app.modules.generator.schemas import (
    CaseCategory,
    DraftAnswers,
    GeneratedBatch,
    GenerationState,
    GenerationStatus,
    TaskSpec,
    TaskType,
)
from app.modules.generator.service import PROMPTS_DIR, channel
from app.modules.prompts.schemas import PromptVersionOut
from app.modules.prompts.service import PromptService
from app.modules.registry.service import RegistryService

CONFIG = Path(__file__).parent / "config"
EVALUATOR_CATALOG = Path(__file__).parents[1] / "evaluation" / "config" / "catalog.yaml"
BALANCE_CASES_PER_LABEL = 2
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
        run = _Run(self, project_id, version_id, state, spec, record)
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


class _Run:
    """The state of one generation run: the spec, prompt, sections and kept embeddings."""

    def __init__(
        self,
        pipeline: GenerationPipeline,
        project_id: uuid.UUID,
        version_id: uuid.UUID,
        state: GenerationState,
        spec: TaskSpec,
        record: TaskSpecRecord,
    ) -> None:
        self.p = pipeline
        self.settings = pipeline._settings
        self.project_id = project_id
        self.version_id = version_id
        self.state = state
        self.spec = spec
        self.record = record
        self.prompt: PromptVersionOut | None = None
        self.sections: list[str] = []
        self.kept: list[list[float]] | None = None

    def _model(self) -> str:
        return self.record.generator_model or ""

    def _call(self, step: str) -> tuple[uuid.UUID, CallPurpose, CallContext]:
        labels = {"step": step, "dataset_version": str(self.version_id)}
        assert self.record.generator_credential_id is not None
        return (
            self.record.generator_credential_id,
            CallPurpose.GENERATION,
            CallContext(project_id=self.project_id, labels=labels),
        )

    async def _items(self, where: ItemFilter | None = None) -> list[DatasetItem]:
        return await self.p._datasets.items(self.version_id, where)

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self.p._embedder.embed, texts) if texts else []

    async def counts(self) -> dict[str, int]:
        totals: dict[str, int] = {}
        for item in await self._items():
            totals[item.source.value] = totals.get(item.source.value, 0) + 1
        return totals

    async def generate(self, only: CaseCategory | None) -> None:
        items = await self._items()
        self.kept = await self._embed([case_text(item.inputs) for item in items])
        real: dict[str, int] = {}
        for item in items:
            if item.source is not ItemSource.GENERATED:
                real[item.category] = real.get(item.category, 0) + 1
        made: dict[str, int] = {}
        for item in items:
            if item.source is ItemSource.GENERATED:
                made[item.category] = made.get(item.category, 0) + 1
        for _ in range(1 + self.settings.generator_top_up_rounds):
            targets = plan_targets(self.p._categories, self.state.target_size, real, made)
            if only is not None:
                targets = {only: targets[only]}
            total = sum(targets.values())
            if total == 0:
                return
            progress = 0
            for category, needed in targets.items():
                while needed > 0:
                    count = min(needed, self.settings.generator_batch_size)
                    added = await self._batch(category, count, target_label=None)
                    made[category] = made.get(category, 0) + added
                    progress += added
                    await self.p._publish(self.version_id, "generate", processed=progress, total=total)
                    if added == 0:
                        break
                    needed -= added

    async def _batch(self, category: CaseCategory, count: int, target_label: str | None) -> int:
        assert self.prompt is not None
        assert self.kept is not None
        examples = await self._items(ItemFilter(source=ItemSource.GOLDEN)) or await self._items(
            ItemFilter(source=ItemSource.INPUT_FILE)
        )
        sections = [section[: self.settings.generator_section_chars] for section in self.sections]
        text = render_system_prompt(
            PROMPTS_DIR,
            "cases.jinja",
            category=category.value,
            count=count,
            instruction=self.p._categories.categories[category].instruction,
            target_label=target_label,
            input_variables=self.spec.input_variables,
            spec=self.spec.model_dump(mode="json"),
            system_template=self.prompt.system_template,
            user_template=self.prompt.user_template,
            examples=[item.inputs for item in examples[: self.settings.generator_example_rows]],
            sections=sections,
        )
        batch = await self.p._gateway.complete_json(
            self._model(), [Message(role="user", content=text)], GeneratedBatch, *self._call(f"cases:{category.value}")
        )
        valid = [case for case in batch.cases if self._valid(case.inputs)]
        self.state.dropped_invalid += len(batch.cases) - len(valid)
        vectors = await self._embed([case_text(case.inputs) for case in valid])
        dropped = set(near_duplicates(self.kept, vectors, self.settings.dedupe_similarity))
        self.state.dropped_duplicates += len(dropped)
        rows: list[dict[str, Any]] = []
        for index, case in enumerate(valid):
            if index in dropped or len(rows) == count:
                continue
            self.kept.append(vectors[index])
            grounded = case.section is not None and 0 <= case.section < len(self.sections)
            rows.append(
                {
                    "inputs": {name: case.inputs[name] for name in self.spec.input_variables},
                    "expected_output": target_label,
                    "rubric": None,
                    "category": category.value,
                    "tags": [],
                    "source": ItemSource.GENERATED,
                    "review_status": ReviewStatus.DRAFT,
                    "context": [self.sections[case.section]] if grounded and case.section is not None else [],
                    "extra": {},
                }
            )
        await self.p._datasets.add_items(self.version_id, rows)
        await self.p._session.commit()
        return len(rows)

    def _valid(self, inputs: dict[str, str]) -> bool:
        return all(not is_blank(inputs.get(name)) for name in self.spec.input_variables)

    async def draft_answers(self) -> None:
        drafts = [
            item
            for item in await self._items(ItemFilter(review_status=ReviewStatus.DRAFT))
            if item.expected_output is None and not item.rubric
        ]
        single = is_single_answer(self.spec)
        size = self.settings.generator_answer_batch_size
        for start in range(0, len(drafts), size):
            batch = drafts[start : start + size]
            text = render_system_prompt(
                PROMPTS_DIR,
                "answers.jinja",
                single_answer=single,
                spec=self.spec.model_dump(mode="json"),
                system_template=self.prompt.system_template if self.prompt else None,
                user_template=self.prompt.user_template if self.prompt else None,
                cases=[{"id": i, "inputs": item.inputs, "context": item.context} for i, item in enumerate(batch)],
            )
            answers = await self.p._gateway.complete_json(
                self._model(), [Message(role="user", content=text)], DraftAnswers, *self._call("answers")
            )
            for answer in answers.answers:
                if not 0 <= answer.id < len(batch):
                    continue
                expected, rubric = self._answer(answer.expected_output, answer.rubric, single)
                if expected is not None or rubric:
                    await self.p._datasets.set_answer(self.version_id, batch[answer.id].id, expected, rubric)
            await self.p._session.commit()
            done = min(start + size, len(drafts))
            await self.p._publish(self.version_id, "answers", processed=done, total=len(drafts))

    def _answer(
        self, expected: str | None, rubric: list[str] | None, single: bool
    ) -> tuple[str | None, list[str] | None]:
        if not single:
            criteria = [c.strip() for c in rubric or [] if c.strip()]
            return None, criteria or None
        if expected is None or not expected.strip():
            return None, None
        if self.spec.task_type is TaskType.CLASSIFICATION and self.spec.allowed_outputs:
            return answer_label(expected, self.spec.allowed_outputs), None
        return expected.strip(), None

    async def balance_labels(self) -> None:
        answers = [item.expected_output for item in await self._items()]
        for label in missing_labels(self.spec, answers):
            await self._batch(CaseCategory.HAPPY_PATH, BALANCE_CASES_PER_LABEL, target_label=label)
