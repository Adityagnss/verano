"""
One Eval Generator run (DEVELOPMENT.md 2.3 Steps B-D) over a draft dataset version:
generate the missing cases per category, validate and dedupe each batch against every
case kept so far, draft expected outputs or rubrics for draft rows, and cover missing
classification labels. The pipeline (`pipeline.py`) creates it and handles state,
evaluators and failures.
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.templates import render_system_prompt
from app.core.text import clip
from app.modules.datasets.domain import is_blank
from app.modules.datasets.models import DatasetItem
from app.modules.datasets.schemas import ItemFilter, ItemSource, ReviewStatus
from app.modules.datasets.service import DatasetService
from app.modules.gateway.schemas import CallContext, CallPurpose, Message
from app.modules.gateway.service import GatewayService
from app.modules.generator.domain import (
    GenerationCatalog,
    answer_label,
    case_text,
    is_single_answer,
    missing_labels,
    near_duplicates,
    plan_targets,
)
from app.modules.generator.models import TaskSpecRecord
from app.modules.generator.plugins.embedders import Embedder
from app.modules.generator.schemas import (
    CaseCategory,
    DraftAnswers,
    GeneratedBatch,
    GeneratedCase,
    GenerationState,
    TaskSpec,
    TaskType,
)
from app.modules.generator.service import PROMPTS_DIR
from app.modules.prompts.schemas import PromptVersionOut

BALANCE_CASES_PER_LABEL = 2
Publish = Callable[..., Awaitable[None]]


@dataclass(frozen=True)
class RunDeps:
    settings: Settings
    session: AsyncSession
    datasets: DatasetService
    embedder: Embedder
    categories: GenerationCatalog
    gateway: GatewayService
    publish: Publish


class GenerationRun:
    """One generation run: the spec, prompt, sections and the embeddings of every kept case."""

    def __init__(
        self,
        deps: RunDeps,
        project_id: uuid.UUID,
        version_id: uuid.UUID,
        state: GenerationState,
        spec: TaskSpec,
        record: TaskSpecRecord,
    ) -> None:
        self.deps = deps
        self.settings = deps.settings
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
        return await self.deps.datasets.items(self.version_id, where)

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self.deps.embedder.embed, texts) if texts else []

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
            targets = plan_targets(self.deps.categories, self.state.target_size, real, made)
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
                    await self.deps.publish(self.version_id, "generate", processed=progress, total=total)
                    if added == 0:
                        break
                    needed -= added

    async def _batch(self, category: CaseCategory, count: int, target_label: str | None) -> int:
        assert self.kept is not None
        batch = await self.deps.gateway.complete_json(
            self._model(),
            [Message(role="user", content=await self._cases_prompt(category, count, target_label))],
            GeneratedBatch,
            *self._call(f"cases:{category.value}"),
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
            rows.append(self._row(case, category, target_label))
        await self.deps.datasets.add_items(self.version_id, rows)
        await self.deps.session.commit()
        return len(rows)

    async def _cases_prompt(self, category: CaseCategory, count: int, target_label: str | None) -> str:
        assert self.prompt is not None
        examples = await self._items(ItemFilter(source=ItemSource.GOLDEN)) or await self._items(
            ItemFilter(source=ItemSource.INPUT_FILE)
        )
        return render_system_prompt(
            PROMPTS_DIR,
            "cases.jinja",
            category=category.value,
            count=count,
            instruction=self.deps.categories.categories[category].instruction,
            target_label=target_label,
            input_variables=self.spec.input_variables,
            spec=self.spec.model_dump(mode="json"),
            system_template=self.prompt.system_template,
            user_template=self.prompt.user_template,
            examples=[clip(item.inputs) for item in examples[: self.settings.generator_example_rows]],
            sections=[section[: self.settings.generator_section_chars] for section in self.sections],
        )

    def _row(self, case: GeneratedCase, category: CaseCategory, target_label: str | None) -> dict[str, Any]:
        grounded = case.section is not None and 0 <= case.section < len(self.sections)
        return {
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
            answers = await self.deps.gateway.complete_json(
                self._model(), [Message(role="user", content=text)], DraftAnswers, *self._call("answers")
            )
            for answer in answers.answers:
                if not 0 <= answer.id < len(batch):
                    continue
                expected, rubric = self._answer(answer.expected_output, answer.rubric, single)
                if expected is not None or rubric:
                    await self.deps.datasets.set_answer(self.version_id, batch[answer.id].id, expected, rubric)
            await self.deps.session.commit()
            done = min(start + size, len(drafts))
            await self.deps.publish(self.version_id, "answers", processed=done, total=len(drafts))

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
