"""
Human labels and judge agreement use cases (ADR 0017).

A person labels an answer good, bad or unsure, with an optional note. The label is stored beside the scores and
never changes one. Every label is kept; an answer shows the majority and the split. Agreement compares each
judged check's pass or fail with the people's majority on the answers they labelled, with the thresholds and the
minimum number of labels coming from settings. Blind review leaves the judge's fields out of the response itself.
"""

import uuid
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import NotFound
from app.core.security import Principal
from app.modules.engine.repository import EngineRepository
from app.modules.engine.schemas import RunStatus
from app.modules.evaluation.agreement import agreement, majority
from app.modules.evaluation.models import HumanLabel
from app.modules.evaluation.repository import LabelRepository, ScoreRepository
from app.modules.evaluation.schemas import (
    AgreementOut,
    EvaluationRunStatus,
    LabelIn,
    LabelOut,
    LabelSummary,
    LabelVerdict,
    ScoreStatus,
)

NO_SUCH_ANSWER = "This answer doesn't belong to this experiment, or it has no output to label."
NOT_SCORED = "This experiment hasn't been scored yet, so there is no judge to compare with people."
TOO_FEW = "Only {n} answers are labelled; at least {minimum} are needed before the agreement can be trusted."
LOW = "The judge disagrees with people too often to rely on: agree on {raw} of answers, kappa {kappa}."
FINE = "The judge agrees with people on {raw} of the labelled answers (kappa {kappa})."
NO_KAPPA = "n/a"


def label_out(row: HumanLabel) -> LabelOut:
    return LabelOut(
        test_case_run_id=row.test_case_run_id,
        user_id=row.user_id,
        verdict=LabelVerdict(row.verdict),
        note=row.note,
        updated_at=row.updated_at,
    )


def summaries(labels: list[HumanLabel], user_id: uuid.UUID | None) -> dict[uuid.UUID, LabelSummary]:
    """One summary per labelled answer: the majority, the split and this user's own label."""
    grouped: dict[uuid.UUID, list[HumanLabel]] = defaultdict(list)
    for label in labels:
        grouped[label.test_case_run_id].append(label)
    found = {}
    for run_id, rows in grouped.items():
        result = majority([row.verdict for row in rows])
        mine = next((LabelVerdict(row.verdict) for row in rows if row.user_id == user_id), None)
        found[run_id] = LabelSummary(
            verdict=result.verdict, good=result.good, bad=result.bad, unsure=result.unsure, mine=mine
        )
    return found


class LabelService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._engine = EngineRepository(session)
        self._labels = LabelRepository(session)
        self._scores = ScoreRepository(session)
        self._settings = settings

    async def set_label(
        self,
        project_id: uuid.UUID,
        experiment_id: uuid.UUID,
        principal: Principal,
        test_case_run_id: uuid.UUID,
        body: LabelIn,
    ) -> LabelOut:
        await self._answer(project_id, experiment_id, test_case_run_id)
        row = await self._labels.set(experiment_id, test_case_run_id, principal.user_id, body.verdict.value, body.note)
        return label_out(row)

    async def remove_label(
        self, project_id: uuid.UUID, experiment_id: uuid.UUID, principal: Principal, test_case_run_id: uuid.UUID
    ) -> None:
        await self._answer(project_id, experiment_id, test_case_run_id)
        await self._labels.remove(experiment_id, test_case_run_id, principal.user_id)

    async def labels(self, project_id: uuid.UUID, experiment_id: uuid.UUID) -> list[LabelOut]:
        await self._experiment(project_id, experiment_id)
        return [label_out(row) for row in await self._labels.for_experiment(experiment_id)]

    async def agreement(
        self, project_id: uuid.UUID, experiment_id: uuid.UUID, run_id: uuid.UUID | None
    ) -> list[AgreementOut]:
        """Per judged check: agreement of its pass or fail with the people's majority on labelled answers."""
        await self._experiment(project_id, experiment_id)
        runs = await self._scores.runs(experiment_id)
        run = (
            next((r for r in runs if r.id == run_id), None)
            if run_id
            else next((r for r in runs if r.status is EvaluationRunStatus.COMPLETED), None)
        )
        if run is None:
            raise NotFound(NOT_SCORED)
        labelled = summaries(await self._labels.for_experiment(experiment_id), None)
        scores = await self._scores.scores(experiment_id, run.id)
        settings = self._settings
        by_check: dict[str, list[tuple[bool, bool]]] = defaultdict(list)
        skipped: dict[str, int] = defaultdict(int)
        for score in scores:
            summary = labelled.get(score.test_case_run_id)
            if summary is None or score.status != ScoreStatus.SCORED or not _judged(score.extra):
                continue
            if summary.verdict in ("good", "bad"):
                by_check[score.evaluator_name].append((score.passed, summary.verdict == "good"))
            else:
                skipped[score.evaluator_name] += 1
        found = []
        for name, pairs in sorted(by_check.items()):
            stats = agreement(
                pairs,
                min_labels=settings.label_min_for_agreement,
                raw_threshold=settings.agreement_min_raw,
                kappa_threshold=settings.agreement_min_kappa,
            )
            raw = "n/a" if stats.raw is None else f"{stats.raw:.0%}"
            kappa = NO_KAPPA if stats.kappa is None else f"{stats.kappa:.2f}"
            message = (
                TOO_FEW.format(n=stats.n, minimum=settings.label_min_for_agreement)
                if stats.too_few
                else (LOW if stats.warn else FINE).format(raw=raw, kappa=kappa)
            )
            found.append(
                AgreementOut(
                    evaluator_name=name,
                    labelled_answers=stats.n + skipped[name],
                    answers_used=stats.n,
                    unsure_or_disputed=skipped[name],
                    raw=stats.raw,
                    kappa=stats.kappa,
                    true_pass=stats.tp,
                    false_pass=stats.fp,
                    false_fail=stats.fn,
                    true_fail=stats.tn,
                    too_few=stats.too_few,
                    warn=stats.warn,
                    min_labels=settings.label_min_for_agreement,
                    raw_threshold=settings.agreement_min_raw,
                    kappa_threshold=settings.agreement_min_kappa,
                    message=message,
                )
            )
        return found

    async def summaries_for(self, experiment_id: uuid.UUID, user_id: uuid.UUID | None) -> dict[uuid.UUID, LabelSummary]:
        return summaries(await self._labels.for_experiment(experiment_id), user_id)

    async def _experiment(self, project_id: uuid.UUID, experiment_id: uuid.UUID) -> None:
        if await self._engine.experiment(experiment_id, project_id) is None:
            raise NotFound("This experiment doesn't exist in this project.")

    async def _answer(self, project_id: uuid.UUID, experiment_id: uuid.UUID, test_case_run_id: uuid.UUID) -> None:
        await self._experiment(project_id, experiment_id)
        row = await self._engine.run(experiment_id, test_case_run_id)
        if row is None or row.status is not RunStatus.SUCCEEDED:
            raise NotFound(NO_SUCH_ANSWER)


def _judged(extra: dict[str, object]) -> bool:
    """Agreement is about judges, not rules: only scores a judge produced are compared with people."""
    return bool(extra.get("judged"))
