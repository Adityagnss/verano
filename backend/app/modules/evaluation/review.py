"""
The review queue (ADR 0038): giving answers to people to label, their queue and progress, and settling
disagreements.

Assignment goes through the project-member model that exists today: a person can be given answers when they belong
to the project's workspace (asked of the auth service). Labelling itself is the existing label endpoint, so a queue
item is done when its person has labelled the answer. A blind assignment leaves the judge's fields, other people's
labels and any final verdict out of the response itself, not just out of the screen. A disagreement (equal good and
bad labels) is settled by a workspace owner: the final verdict is stored beside the labels and never changes a
score or a label.
"""

import uuid
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import Conflict, NotFound, PermissionDenied, ValidationFailed
from app.core.ids import uuid7
from app.core.pagination import PageParams, encode_cursor
from app.core.security import Principal
from app.modules.auth.schemas import MembershipRole
from app.modules.auth.service import AuthService
from app.modules.datasets.models import DatasetItem
from app.modules.datasets.service import DatasetService
from app.modules.engine.models import Experiment, TestCaseRun
from app.modules.engine.repository import EngineRepository
from app.modules.engine.schemas import RunStatus
from app.modules.evaluation.agreement import majority
from app.modules.evaluation.domain import Score
from app.modules.evaluation.labels import summaries
from app.modules.evaluation.metrics import WeightedScore, case_result
from app.modules.evaluation.models import HumanLabel, ReviewAssignment, ReviewResolution
from app.modules.evaluation.repository import ScoreRepository
from app.modules.evaluation.review_repository import ReviewRepository
from app.modules.evaluation.review_schemas import (
    AssignOut,
    AssignRequest,
    DisputeOut,
    PersonLabel,
    PersonProgress,
    ProgressOut,
    QueueOut,
    QueueStatus,
    ResolutionOut,
    ResolveRequest,
    ReviewItemOut,
    ReviewJudgeOut,
    ReviewMemberOut,
)
from app.modules.evaluation.schemas import EvaluationRunStatus, LabelVerdict, ScoreOut, ScoreStatus
from app.modules.projects.schemas import ProjectOut

NO_EXPERIMENT = "This experiment doesn't exist in this project."
NOT_A_MEMBER = "That person isn't a member of this project's workspace, so they can't be given answers to label."
BAD_ANSWERS = "{n} of those answers don't belong to this experiment or have no output to label."
TOO_MANY = "At most {cap} answers can be given out at once."
NOTHING_LEFT = "There are no more answers of that kind to give out."
ONLY_OWNER = "Only a workspace owner can settle a disagreement between labels."
NOT_DISPUTED = "The labels on this answer don't disagree, so there is nothing to settle."
NO_ASSIGNMENT = "This item isn't in your queue or this project."
NOT_YOURS = "Only the person it was given to, or the person who gave it, can take it off the queue."
NO_ANSWER = "This answer doesn't belong to this experiment, or it has no output."


def resolution_out(row: ReviewResolution) -> ResolutionOut:
    return ResolutionOut(
        verdict=LabelVerdict(row.verdict), note=row.note, resolved_by=row.resolved_by, updated_at=row.updated_at
    )


def disputed_ids(labels: list[HumanLabel]) -> list[uuid.UUID]:
    """Answers whose labels disagree: as many good as bad, in the order they were first labelled."""
    grouped: dict[uuid.UUID, list[str]] = defaultdict(list)
    for label in labels:
        grouped[label.test_case_run_id].append(label.verdict)
    return [run_id for run_id, verdicts in grouped.items() if majority(verdicts).verdict == "disputed"]


def judge_view(scores: list[ScoreOut], weights: dict[str, float]) -> ReviewJudgeOut:
    """The judge's verdict and quality on one answer, from the same rule the results use."""
    weighted = [
        WeightedScore(
            Score(s.value, s.passed, s.reason), weights.get(s.evaluator_name, 1.0), s.status is ScoreStatus.SCORED
        )
        for s in scores
    ]
    passed, quality, judged = case_result(weighted)
    return ReviewJudgeOut(passed=passed if judged else None, quality=quality if judged else None, scores=scores)


class ReviewService:
    def __init__(self, session: AsyncSession, settings: Settings, auth: AuthService) -> None:
        self._settings = settings
        self._auth = auth
        self._repo = ReviewRepository(session)
        self._engine = EngineRepository(session)
        self._scores = ScoreRepository(session)
        self._datasets = DatasetService(session, settings)

    # -- people ---------------------------------------------------------------------------------------------

    async def members(self, project: ProjectOut) -> list[ReviewMemberOut]:
        """The people in this project's workspace, who can be given answers to label."""
        return [
            ReviewMemberOut(user_id=user.id, name=user.name, email=user.email, is_owner=role is MembershipRole.OWNER)
            for user, role in await self._auth.organization_members(project.organization_id)
        ]

    async def _names(self, project: ProjectOut) -> dict[uuid.UUID, str]:
        return {m.user_id: m.name for m in await self.members(project)}

    async def _require_member(self, project: ProjectOut, user_id: uuid.UUID) -> None:
        if project.organization_id not in await self._auth.organization_ids(user_id):
            raise ValidationFailed(NOT_A_MEMBER)

    async def _require_owner(self, project: ProjectOut, principal: Principal) -> None:
        owns = any(
            org.id == project.organization_id and org.role is MembershipRole.OWNER
            for org in await self._auth.organizations(principal.user_id)
        )
        if not owns:
            raise PermissionDenied(ONLY_OWNER)

    # -- assigning ------------------------------------------------------------------------------------------

    async def assign(self, project: ProjectOut, principal: Principal, body: AssignRequest) -> AssignOut:
        experiment = await self._experiment(project.id, body.experiment_id)
        assignee = body.assignee_user_id or principal.user_id
        await self._require_member(project, assignee)
        cap = self._settings.review_queue_max_assign
        skipped = 0
        if body.test_case_run_ids is not None:
            wanted = list(dict.fromkeys(body.test_case_run_ids))
            if len(wanted) > cap:
                raise ValidationFailed(TOO_MANY.format(cap=cap))
            runs = await self._engine.runs(experiment.id, wanted)
            good = {r.id for r in runs if r.status is RunStatus.SUCCEEDED}
            if len(good) != len(wanted):
                raise ValidationFailed(BAD_ANSWERS.format(n=len(wanted) - len(good)))
            labelled = {
                x.test_case_run_id for x in await self._repo.labels_of(experiment.id, wanted) if x.user_id == assignee
            }
            chosen = [run_id for run_id in wanted if run_id not in labelled]
            skipped = len(wanted) - len(chosen)
        else:
            assert body.count is not None
            if body.count > cap:
                raise ValidationFailed(TOO_MANY.format(cap=cap))
            chosen = await self._pick(experiment.id, assignee, body.pick, body.count)
        rows = [
            {
                "id": uuid7(),
                "project_id": project.id,
                "experiment_id": experiment.id,
                "test_case_run_id": run_id,
                "assignee_user_id": assignee,
                "assigned_by": principal.user_id,
                "blind": body.blind,
                "batch_label": body.batch_label,
            }
            for run_id in chosen
        ]
        added = await self._repo.add_assignments(rows)
        name = (await self._names(project)).get(assignee, "that person")
        if not chosen and body.count is not None:
            message = NOTHING_LEFT
        else:
            message = f"Gave {added} answer{'s' if added != 1 else ''} to {name} to label."
        return AssignOut(
            assignee_user_id=assignee,
            assigned=added,
            already_assigned=len(chosen) - added,
            skipped=skipped,
            message=message,
        )

    async def _pick(self, experiment_id: uuid.UUID, assignee: uuid.UUID, pick: str, count: int) -> list[uuid.UUID]:
        if pick == "unlabelled":
            return await self._repo.unlabelled_answers(experiment_id, assignee, count)
        labels = await self._repo.all_labels(experiment_id)
        settled = {r.test_case_run_id for r in await self._repo.resolutions(experiment_id, None)}
        mine = {x.test_case_run_id for x in labels if x.user_id == assignee}
        taken = await self._repo.assigned_ids(experiment_id, assignee)
        return [r for r in disputed_ids(labels) if r not in settled and r not in mine and r not in taken][:count]

    async def unassign(self, project: ProjectOut, principal: Principal, assignment_id: uuid.UUID) -> None:
        row = await self._repo.assignment(project.id, assignment_id)
        if row is None:
            raise NotFound(NO_ASSIGNMENT)
        if principal.user_id not in (row.assignee_user_id, row.assigned_by):
            raise PermissionDenied(NOT_YOURS)
        await self._repo.remove_assignment(row.id)

    # -- the queue ------------------------------------------------------------------------------------------

    async def queue(
        self,
        project: ProjectOut,
        principal: Principal,
        status: QueueStatus,
        experiment_id: uuid.UUID | None,
        page: PageParams,
        blind: bool = False,
    ) -> QueueOut:
        """This person's queue, oldest first. In a blind review the judge's scores, verdict, other people's labels
        and any final verdict are never loaded, so they cannot appear in the response."""
        found = await self._repo.queue(project.id, principal.user_id, status, experiment_id, page.cursor, page.limit)
        more = len(found) > page.limit
        found = found[: page.limit]
        by_experiment: dict[uuid.UUID, list[tuple[ReviewAssignment, bool]]] = defaultdict(list)
        for assignment, done in found:
            by_experiment[assignment.experiment_id].append((assignment, done))
        items: dict[uuid.UUID, ReviewItemOut] = {}
        for eid, group in by_experiment.items():
            experiment = await self._experiment(project.id, eid)
            items |= await self._items(experiment, principal, group, blind)
        counts = await self._repo.counts(project.id, principal.user_id, experiment_id)
        assigned = sum(c[1] for c in counts)
        done_total = sum(c[2] for c in counts)
        return QueueOut(
            items=[items[a.id] for a, _ in found if a.id in items],
            next_cursor=encode_cursor(found[-1][0].id) if more and found else None,
            open=assigned - done_total,
            done=done_total,
        )

    async def _items(
        self,
        experiment: Experiment,
        principal: Principal,
        group: list[tuple[ReviewAssignment, bool]],
        force_blind: bool,
    ) -> dict[uuid.UUID, ReviewItemOut]:
        run_ids = [a.test_case_run_id for a, _ in group]
        runs: dict[uuid.UUID, TestCaseRun] = {r.id: r for r in await self._engine.runs(experiment.id, run_ids)}
        cases: dict[uuid.UUID, DatasetItem] = {
            i.id: i
            for i in await self._datasets.items(
                experiment.dataset_version_id, ids=[r.dataset_item_id for r in runs.values()]
            )
        }
        seeing = [a.test_case_run_id for a, _ in group if not (a.blind or force_blind)]
        labels = await self._repo.labels_of(experiment.id, run_ids)
        summary = summaries(labels, principal.user_id)
        mine = {x.test_case_run_id: x for x in labels if x.user_id == principal.user_id}
        resolutions = (
            {r.test_case_run_id: r for r in await self._repo.resolutions(experiment.id, seeing)} if seeing else {}
        )
        scores: dict[uuid.UUID, list[ScoreOut]] = defaultdict(list)
        weights: dict[str, float] = {}
        if seeing:
            passes = await self._scores.runs(experiment.id)
            latest = next((r for r in passes if r.status is EvaluationRunStatus.COMPLETED), None)
            if latest is not None:
                for s in await self._repo.scores_of(experiment.id, latest.id, seeing):
                    weights[s.evaluator_name] = s.weight
                    scores[s.test_case_run_id].append(
                        ScoreOut(
                            evaluator_name=s.evaluator_name,
                            value=s.value,
                            passed=s.passed,
                            reason=s.reason,
                            status=ScoreStatus(s.status),
                        )
                    )
        out: dict[uuid.UUID, ReviewItemOut] = {}
        for assignment, done in group:
            run = runs.get(assignment.test_case_run_id)
            case = cases.get(run.dataset_item_id) if run else None
            if run is None or case is None:
                continue
            hidden = assignment.blind or force_blind
            label = mine.get(run.id)
            resolution = resolutions.get(run.id)
            shown = scores.get(run.id)
            out[assignment.id] = ReviewItemOut(
                assignment_id=assignment.id,
                experiment_id=experiment.id,
                experiment_name=experiment.name,
                test_case_run_id=run.id,
                assigned_at=assignment.created_at,
                batch_label=assignment.batch_label,
                blind=hidden,
                done=done,
                inputs=case.inputs,
                expected_output=case.expected_output,
                rubric=case.rubric,
                output=run.raw_output,
                truncated=run.output_truncated,
                model=run.model,
                retrieved_chunks=run.retrieved_chunks,
                tool_calls=run.tool_calls,
                my_label=LabelVerdict(label.verdict) if label else None,
                my_note=label.note if label else None,
                judge=None if hidden or shown is None else judge_view(shown, weights),
                labels=None if hidden else summary.get(run.id),
                resolution=None if hidden or resolution is None else resolution_out(resolution),
                hidden=hidden,
            )
        return out

    # -- progress -------------------------------------------------------------------------------------------

    async def progress(self, project: ProjectOut, experiment_id: uuid.UUID | None) -> ProgressOut:
        """Who has been given how many answers and how many they have labelled, and how many disagreements wait."""
        names = await self._names(project)
        people = [
            PersonProgress(
                user_id=user, name=names.get(user, "Former member"), assigned=assigned, done=done, open=assigned - done
            )
            for user, assigned, done in await self._repo.counts(project.id, None, experiment_id)
        ]
        people.sort(key=lambda p: (p.name.lower(), str(p.user_id)))
        disputed = resolved = 0
        if experiment_id is not None:
            await self._experiment(project.id, experiment_id)
            labels = await self._repo.all_labels(experiment_id)
            settled = {r.test_case_run_id for r in await self._repo.resolutions(experiment_id, None)}
            ids = disputed_ids(labels)
            disputed = sum(1 for r in ids if r not in settled)
            resolved = len(settled)
        assigned = sum(p.assigned for p in people)
        done = sum(p.done for p in people)
        return ProgressOut(
            people=people, assigned=assigned, done=done, open=assigned - done, disputed=disputed, resolved=resolved
        )

    # -- disagreements --------------------------------------------------------------------------------------

    async def disputes(self, project: ProjectOut, experiment_id: uuid.UUID, include_settled: bool) -> list[DisputeOut]:
        """Answers whose labels disagree (and, if asked, those already settled), with who said what."""
        experiment = await self._experiment(project.id, experiment_id)
        labels = await self._repo.all_labels(experiment.id)
        resolutions = {r.test_case_run_id: r for r in await self._repo.resolutions(experiment.id, None)}
        wanted = [r for r in disputed_ids(labels) if include_settled or r not in resolutions]
        wanted += [r for r in resolutions if include_settled and r not in wanted]
        if not wanted:
            return []
        names = await self._names(project)
        runs = {r.id: r for r in await self._engine.runs(experiment.id, wanted)}
        cases = {
            i.id: i
            for i in await self._datasets.items(
                experiment.dataset_version_id, ids=[r.dataset_item_id for r in runs.values()]
            )
        }
        said: dict[uuid.UUID, list[PersonLabel]] = defaultdict(list)
        for label in labels:
            said[label.test_case_run_id].append(
                PersonLabel(
                    user_id=label.user_id,
                    name=names.get(label.user_id, "Former member"),
                    verdict=LabelVerdict(label.verdict),
                    note=label.note,
                )
            )
        found = []
        for run_id in wanted:
            run = runs.get(run_id)
            case = cases.get(run.dataset_item_id) if run else None
            if run is None or case is None:
                continue
            settled = resolutions.get(run_id)
            found.append(
                DisputeOut(
                    experiment_id=experiment.id,
                    test_case_run_id=run_id,
                    inputs=case.inputs,
                    expected_output=case.expected_output,
                    output=run.raw_output,
                    labels=said.get(run_id, []),
                    resolution=resolution_out(settled) if settled else None,
                )
            )
        return found

    async def resolve(
        self,
        project: ProjectOut,
        principal: Principal,
        experiment_id: uuid.UUID,
        test_case_run_id: uuid.UUID,
        body: ResolveRequest,
    ) -> ResolutionOut:
        """Settles a disagreement. Stored beside the labels; no score and no label changes."""
        await self._require_owner(project, principal)
        await self._answer(project.id, experiment_id, test_case_run_id)
        labels = await self._repo.labels_of(experiment_id, [test_case_run_id])
        existing = await self._repo.resolutions(experiment_id, [test_case_run_id])
        if not existing and majority([x.verdict for x in labels]).verdict != "disputed":
            raise Conflict(NOT_DISPUTED)
        row = await self._repo.set_resolution(
            experiment_id, test_case_run_id, body.verdict.value, body.note, principal.user_id
        )
        return resolution_out(row)

    async def unresolve(
        self, project: ProjectOut, principal: Principal, experiment_id: uuid.UUID, test_case_run_id: uuid.UUID
    ) -> None:
        await self._require_owner(project, principal)
        await self._answer(project.id, experiment_id, test_case_run_id)
        await self._repo.remove_resolution(experiment_id, test_case_run_id)

    # -- shared ---------------------------------------------------------------------------------------------

    async def _experiment(self, project_id: uuid.UUID, experiment_id: uuid.UUID) -> Experiment:
        experiment = await self._engine.experiment(experiment_id, project_id)
        if experiment is None:
            raise NotFound(NO_EXPERIMENT)
        return experiment

    async def _answer(self, project_id: uuid.UUID, experiment_id: uuid.UUID, test_case_run_id: uuid.UUID) -> None:
        await self._experiment(project_id, experiment_id)
        row = await self._engine.run(experiment_id, test_case_run_id)
        if row is None or row.status is not RunStatus.SUCCEEDED:
            raise NotFound(NO_ANSWER)
