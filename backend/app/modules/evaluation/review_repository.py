"""
Review queue data access (ADR 0038). Every read is one bulk query over an index; nothing loops over rows.

An assignment is done when its assignee has a label on the answer, which is read with an EXISTS against
`human_labels`, so the queue and the labels can never disagree.
"""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import and_, delete, exists, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.engine.models import TestCaseRun
from app.modules.engine.schemas import RunStatus
from app.modules.evaluation.models import HumanLabel, ReviewAssignment, ReviewResolution, Score
from app.modules.evaluation.review_schemas import QueueStatus


def _has_label() -> Any:
    """True when the assignment's person has labelled the answer."""
    return exists().where(
        HumanLabel.experiment_id == ReviewAssignment.experiment_id,
        HumanLabel.test_case_run_id == ReviewAssignment.test_case_run_id,
        HumanLabel.user_id == ReviewAssignment.assignee_user_id,
    )


class ReviewRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_assignments(self, rows: list[dict[str, Any]]) -> int:
        """Inserts the assignments that do not exist yet and returns how many were new."""
        if not rows:
            return 0
        statement = (
            pg_insert(ReviewAssignment)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["experiment_id", "test_case_run_id", "assignee_user_id"])
            .returning(ReviewAssignment.id)
        )
        return len((await self._session.scalars(statement)).all())

    async def assignment(self, project_id: uuid.UUID, assignment_id: uuid.UUID) -> ReviewAssignment | None:
        query = select(ReviewAssignment).where(
            ReviewAssignment.id == assignment_id, ReviewAssignment.project_id == project_id
        )
        return await self._session.scalar(query)

    async def remove_assignment(self, assignment_id: uuid.UUID) -> None:
        await self._session.execute(delete(ReviewAssignment).where(ReviewAssignment.id == assignment_id))

    async def queue(
        self,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        status: QueueStatus,
        experiment_id: uuid.UUID | None,
        after: uuid.UUID | None,
        limit: int,
    ) -> list[tuple[ReviewAssignment, bool]]:
        """One person's assignments oldest first (the order they were given), with whether each is done."""
        done = _has_label().label("done")
        query = select(ReviewAssignment, done).where(
            ReviewAssignment.project_id == project_id, ReviewAssignment.assignee_user_id == user_id
        )
        if experiment_id is not None:
            query = query.where(ReviewAssignment.experiment_id == experiment_id)
        if status is QueueStatus.OPEN:
            query = query.where(~_has_label())
        elif status is QueueStatus.DONE:
            query = query.where(_has_label())
        if after is not None:
            query = query.where(ReviewAssignment.id > after)
        rows = (await self._session.execute(query.order_by(ReviewAssignment.id).limit(limit + 1))).all()
        return [(row[0], bool(row[1])) for row in rows]

    async def counts(
        self, project_id: uuid.UUID, user_id: uuid.UUID | None, experiment_id: uuid.UUID | None
    ) -> list[tuple[uuid.UUID, int, int]]:
        """(person, assigned, done) for one person or everyone, in one grouped query."""
        query = (
            select(ReviewAssignment.assignee_user_id, func.count(), func.count().filter(_has_label()))
            .where(ReviewAssignment.project_id == project_id)
            .group_by(ReviewAssignment.assignee_user_id)
        )
        if user_id is not None:
            query = query.where(ReviewAssignment.assignee_user_id == user_id)
        if experiment_id is not None:
            query = query.where(ReviewAssignment.experiment_id == experiment_id)
        return [(row[0], int(row[1]), int(row[2])) for row in (await self._session.execute(query)).all()]

    async def assigned_ids(self, experiment_id: uuid.UUID, user_id: uuid.UUID) -> set[uuid.UUID]:
        query = select(ReviewAssignment.test_case_run_id).where(
            ReviewAssignment.experiment_id == experiment_id, ReviewAssignment.assignee_user_id == user_id
        )
        return set((await self._session.scalars(query)).all())

    async def unlabelled_answers(self, experiment_id: uuid.UUID, user_id: uuid.UUID, limit: int) -> list[uuid.UUID]:
        """Answers nobody has labelled that this person is not already assigned, in a stable order."""
        query = (
            select(TestCaseRun.id)
            .where(
                TestCaseRun.experiment_id == experiment_id,
                TestCaseRun.status == RunStatus.SUCCEEDED,
                ~exists().where(
                    HumanLabel.experiment_id == TestCaseRun.experiment_id, HumanLabel.test_case_run_id == TestCaseRun.id
                ),
                ~exists().where(
                    ReviewAssignment.experiment_id == TestCaseRun.experiment_id,
                    ReviewAssignment.test_case_run_id == TestCaseRun.id,
                    ReviewAssignment.assignee_user_id == user_id,
                ),
            )
            .order_by(TestCaseRun.id)
            .limit(limit)
        )
        return list((await self._session.scalars(query)).all())

    async def labels_of(self, experiment_id: uuid.UUID, run_ids: Sequence[uuid.UUID]) -> list[HumanLabel]:
        query = select(HumanLabel).where(
            HumanLabel.experiment_id == experiment_id, HumanLabel.test_case_run_id.in_(run_ids)
        )
        return list((await self._session.scalars(query.order_by(HumanLabel.created_at))).all())

    async def scores_of(self, experiment_id: uuid.UUID, run_id: uuid.UUID, run_ids: Sequence[uuid.UUID]) -> list[Score]:
        query = select(Score).where(
            and_(
                Score.experiment_id == experiment_id,
                Score.evaluation_run_id == run_id,
                Score.test_case_run_id.in_(run_ids),
            )
        )
        return list((await self._session.scalars(query)).all())

    async def resolutions(
        self, experiment_id: uuid.UUID, run_ids: Sequence[uuid.UUID] | None
    ) -> list[ReviewResolution]:
        query = select(ReviewResolution).where(ReviewResolution.experiment_id == experiment_id)
        if run_ids is not None:
            query = query.where(ReviewResolution.test_case_run_id.in_(run_ids))
        return list((await self._session.scalars(query.execution_options(populate_existing=True))).all())

    async def set_resolution(
        self, experiment_id: uuid.UUID, run_id: uuid.UUID, verdict: str, note: str | None, user_id: uuid.UUID
    ) -> ReviewResolution:
        """One final verdict per answer: a second one replaces the first."""
        statement = (
            pg_insert(ReviewResolution)
            .values(
                experiment_id=experiment_id,
                test_case_run_id=run_id,
                verdict=verdict,
                note=note,
                resolved_by=user_id,
            )
            .on_conflict_do_update(
                index_elements=["experiment_id", "test_case_run_id"],
                set_={"verdict": verdict, "note": note, "resolved_by": user_id, "updated_at": func.now()},
            )
            .returning(ReviewResolution.id)
        )
        resolution_id = await self._session.scalar(statement)
        row = await self._session.scalar(
            select(ReviewResolution)
            .where(ReviewResolution.id == resolution_id)
            .execution_options(populate_existing=True)
        )
        assert row is not None
        return row

    async def remove_resolution(self, experiment_id: uuid.UUID, run_id: uuid.UUID) -> None:
        await self._session.execute(
            delete(ReviewResolution).where(
                ReviewResolution.experiment_id == experiment_id, ReviewResolution.test_case_run_id == run_id
            )
        )

    async def all_labels(self, experiment_id: uuid.UUID) -> list[HumanLabel]:
        query = select(HumanLabel).where(HumanLabel.experiment_id == experiment_id).order_by(HumanLabel.created_at)
        return list((await self._session.scalars(query.execution_options(populate_existing=True))).all())
