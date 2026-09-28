"""
Dataset use cases: the project's draft dataset version (created on first use), and the
Review & Approve step (DEVELOPMENT.md 2.4).

A project keeps its test cases in one dataset; its newest version is the working draft
until it is approved. `ensure_draft` finds or creates that draft under the project's
advisory lock, so concurrent imports and generations share one draft.
Review: list and filter cases by source, category, review status or split; add, edit and
delete cases; approve drafts in bulk (per category or source) after spot-checking. Golden
rows are trusted; input-file and generated rows are drafts until approved, and editing a
draft counts as reviewing it. Approving checks that every case is reviewed and has an
expected output or rubric and that an evaluator set exists, then assigns the stratified
70/30 split and freezes the version. A frozen version accepts no changes, and only an
approved version can be used by an experiment (`approved_version`).
Other modules use this service, never the dataset tables.
"""

import random
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.ids import uuid7
from app.core.pagination import Page, PageParams, to_page
from app.core.security import Principal, utcnow
from app.modules.datasets.domain import SplitCandidate, assign_splits
from app.modules.datasets.models import Dataset, DatasetItem, DatasetVersion
from app.modules.datasets.repository import DatasetRepository
from app.modules.datasets.schemas import (
    BulkApprove,
    DatasetVersionOut,
    DatasetVersionStatus,
    GroupCount,
    ItemCreate,
    ItemFilter,
    ItemOut,
    ItemSource,
    ItemUpdate,
    ReviewStatus,
)

VERSION_NOT_FOUND = "This dataset version doesn't exist in this project."
NO_DATASET = "This project has no test cases yet. Upload data or generate test cases first."
ITEM_NOT_FOUND = "This test case doesn't exist in this dataset version."
FROZEN = "Dataset version {version} is approved and frozen. Changes go into a new version."
NOT_APPROVED = "Dataset version {version} isn't approved yet. Review and approve it before running experiments."
GENERATING = "Test cases are still being generated. Wait for generation to finish."
EMPTY = "There are no test cases to approve."
UNREVIEWED = "{count} draft case(s) still need review. Approve them (per category is fine) or edit them."
NO_ANSWER = "{count} case(s) have neither an expected output nor a rubric. Add one or delete the case."
NO_EVALUATORS = "No evaluator set yet. Confirm the Task Spec and run the generator (or 'Use only my golden set')."
SMALL_HOLDOUT = (
    "The holdout will have {holdout} cases. Fewer than {minimum} can't show a clear difference when "
    "improving the prompt; generate more cases."
)


def item_out(row: DatasetItem) -> ItemOut:
    return ItemOut.model_validate(row)


class DatasetService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._repo = DatasetRepository(session)
        self._settings = settings

    async def ensure_draft(self, project_id: uuid.UUID) -> DatasetVersion:
        await self._repo.lock_project(project_id)
        draft = await self._repo.draft_version(project_id)
        if draft is not None:
            return draft
        dataset = await self._repo.latest_dataset(project_id)
        if dataset is None:
            dataset = Dataset(project_id=project_id, name=self._settings.dataset_default_name)
            await self._repo.add(dataset)
        version = DatasetVersion(
            dataset_id=dataset.id,
            version=await self._repo.next_version_number(dataset.id),
            status=DatasetVersionStatus.DRAFT,
        )
        await self._repo.add(version)
        return version

    async def find_draft(self, project_id: uuid.UUID) -> DatasetVersion | None:
        return await self._repo.draft_version(project_id)

    async def current(self, project_id: uuid.UUID) -> DatasetVersionOut:
        version = await self._repo.latest_version(project_id)
        if version is None:
            raise NotFound(NO_DATASET)
        return await self.summary(version)

    async def get_version(self, project_id: uuid.UUID, version_id: uuid.UUID) -> DatasetVersionOut:
        return await self.summary(await self._version(project_id, version_id))

    async def approved_version(self, project_id: uuid.UUID, version_id: uuid.UUID) -> DatasetVersion:
        version = await self._version(project_id, version_id)
        if version.status is not DatasetVersionStatus.APPROVED:
            raise Conflict(NOT_APPROVED.format(version=version.version))
        return version

    async def draft_for_edit(self, project_id: uuid.UUID, version_id: uuid.UUID) -> DatasetVersion:
        version = await self._version(project_id, version_id, lock=True)
        if version.status is DatasetVersionStatus.APPROVED:
            raise Conflict(FROZEN.format(version=version.version))
        return version

    async def summary(self, version: DatasetVersion) -> DatasetVersionOut:
        items = await self._repo.items(version.id)
        by_source: dict[str, GroupCount] = {}
        by_category: dict[str, GroupCount] = {}
        by_split: dict[str, int] = {}
        for item in items:
            for groups, key in ((by_source, item.source.value), (by_category, item.category)):
                group = groups.setdefault(key, GroupCount())
                group.total += 1
                group.draft += item.review_status is ReviewStatus.DRAFT
                group.without_answer += item.expected_output is None and not item.rubric
            if item.split is not None:
                by_split[item.split.value] = by_split.get(item.split.value, 0) + 1
        holdout = by_split.get("holdout", round(len(items) * self._settings.dataset_holdout_ratio))
        warnings = []
        if items and holdout < self._settings.dataset_min_holdout:
            warnings.append(SMALL_HOLDOUT.format(holdout=holdout, minimum=self._settings.dataset_min_holdout))
        return DatasetVersionOut(
            id=version.id,
            dataset_id=version.dataset_id,
            version=version.version,
            status=version.status,
            task_spec_id=version.task_spec_id,
            evaluator_set_version_id=version.evaluator_set_version_id,
            generation=version.generation,
            holdout_ratio=version.holdout_ratio,
            split_seed=version.split_seed,
            approved_at=version.approved_at,
            item_count=len(items),
            by_source=by_source,
            by_category=by_category,
            by_split=by_split,
            warnings=warnings,
        )

    async def list_items(
        self, project_id: uuid.UUID, version_id: uuid.UUID, where: ItemFilter, page: PageParams
    ) -> Page[ItemOut]:
        version = await self._version(project_id, version_id)
        rows = await self._repo.items_page(version.id, where, page)
        return to_page([item_out(row) for row in rows], page, lambda item: item.id)

    async def add_item(self, project_id: uuid.UUID, version_id: uuid.UUID, body: ItemCreate) -> ItemOut:
        version = await self.draft_for_edit(project_id, version_id)
        row = {
            "id": uuid7(),
            "dataset_version_id": version.id,
            **body.model_dump(),
            "source": ItemSource.GOLDEN,
            "review_status": ReviewStatus.TRUSTED,
            "context": [],
            "extra": {},
            "position": await self._repo.next_position(version.id),
        }
        await self._repo.insert_items([row])
        return await self._item(version.id, row["id"])

    async def edit_item(
        self, project_id: uuid.UUID, version_id: uuid.UUID, item_id: uuid.UUID, body: ItemUpdate
    ) -> ItemOut:
        version = await self.draft_for_edit(project_id, version_id)
        item = await self._item_row(version.id, item_id)
        values: dict[str, Any] = body.model_dump(exclude_unset=True)
        if item.review_status is ReviewStatus.DRAFT:
            values["review_status"] = ReviewStatus.APPROVED
        await self._repo.update_items(version.id, values, ids=[item.id])
        return await self._item(version.id, item.id)

    async def delete_item(self, project_id: uuid.UUID, version_id: uuid.UUID, item_id: uuid.UUID) -> None:
        version = await self.draft_for_edit(project_id, version_id)
        await self._item_row(version.id, item_id)
        await self._repo.delete_items(version.id, ids=[item_id])

    async def approve_drafts(
        self, project_id: uuid.UUID, version_id: uuid.UUID, body: BulkApprove
    ) -> DatasetVersionOut:
        version = await self.draft_for_edit(project_id, version_id)
        where = ItemFilter(source=body.source, category=body.category, review_status=ReviewStatus.DRAFT)
        await self._repo.update_items(version.id, {"review_status": ReviewStatus.APPROVED}, where)
        return await self.summary(version)

    async def approve(self, project_id: uuid.UUID, version_id: uuid.UUID, principal: Principal) -> DatasetVersionOut:
        version = await self.draft_for_edit(project_id, version_id)
        if (version.generation or {}).get("status") == "running":
            raise Conflict(GENERATING)
        items = await self._repo.items(version.id)
        problems = []
        if not items:
            problems.append(EMPTY)
        drafts = sum(item.review_status is ReviewStatus.DRAFT for item in items)
        if drafts:
            problems.append(UNREVIEWED.format(count=drafts))
        unanswered = sum(item.expected_output is None and not item.rubric for item in items)
        if unanswered:
            problems.append(NO_ANSWER.format(count=unanswered))
        if version.evaluator_set_version_id is None:
            problems.append(NO_EVALUATORS)
        if problems:
            raise ValidationFailed(" ".join(problems), {"problems": problems})
        seed = random.SystemRandom().randrange(2**31)
        ratio = self._settings.dataset_holdout_ratio
        candidates = [SplitCandidate(item.id, item.category, item.source) for item in items]
        await self._repo.set_splits(assign_splits(candidates, ratio, seed))
        await self._repo.update_version(
            version.id,
            {
                "status": DatasetVersionStatus.APPROVED,
                "holdout_ratio": ratio,
                "split_seed": seed,
                "approved_at": utcnow(),
                "approved_by": principal.user_id,
            },
        )
        return await self.summary(await self._version(project_id, version.id))

    # Used by the Eval Generator.
    async def items(
        self, version_id: uuid.UUID, where: ItemFilter | None = None, ids: list[uuid.UUID] | None = None
    ) -> list[DatasetItem]:
        return await self._repo.items(version_id, where, ids)

    async def add_items(self, version_id: uuid.UUID, rows: list[dict[str, Any]]) -> None:
        position = await self._repo.next_position(version_id)
        await self._repo.insert_items(
            [
                {"id": uuid7(), "dataset_version_id": version_id, **row, "position": position + i}
                for i, row in enumerate(rows)
            ]
        )

    async def set_answer(
        self, version_id: uuid.UUID, item_id: uuid.UUID, expected_output: str | None, rubric: list[str] | None
    ) -> None:
        values = {"expected_output": expected_output, "rubric": rubric}
        await self._repo.update_items(version_id, values, ItemFilter(review_status=ReviewStatus.DRAFT), ids=[item_id])

    async def delete_generated(self, version_id: uuid.UUID, category: str | None = None) -> None:
        await self._repo.delete_items(version_id, ItemFilter(source=ItemSource.GENERATED, category=category))

    async def update_version(self, version_id: uuid.UUID, values: dict[str, Any]) -> None:
        await self._repo.update_version(version_id, values)

    async def _version(self, project_id: uuid.UUID, version_id: uuid.UUID, lock: bool = False) -> DatasetVersion:
        version = await self._repo.version(project_id, version_id, lock=lock)
        if version is None:
            raise NotFound(VERSION_NOT_FOUND)
        return version

    async def _item_row(self, version_id: uuid.UUID, item_id: uuid.UUID) -> DatasetItem:
        item = await self._repo.item(version_id, item_id)
        if item is None:
            raise NotFound(ITEM_NOT_FOUND)
        return item

    async def _item(self, version_id: uuid.UUID, item_id: uuid.UUID) -> ItemOut:
        return item_out(await self._item_row(version_id, item_id))
