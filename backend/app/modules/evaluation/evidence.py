"""
"Why this score": the evidence and the limits behind every score of one answer.

For each check that scored the answer: what kind of check it is (a program, a judge or the user's own code), the
reason it gave, whether the result came from the cache, how many answers that check scored and could not score
in the whole pass, what the check cannot tell (in words, from data), and, for a judge, how often it agrees with
people when enough answers were labelled. Nothing here changes a score.
"""

import uuid
from collections import Counter

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import NotFound
from app.modules.engine.repository import EngineRepository
from app.modules.evaluation.gallery import NOT_MEASURED, gallery
from app.modules.evaluation.labels import LabelService
from app.modules.evaluation.plugins.rules_extra import RULE_INFO
from app.modules.evaluation.repository import EvaluatorRepository, ScoreRepository
from app.modules.evaluation.schemas import (
    AgreementOut,
    EvaluationRunStatus,
    EvidenceOut,
    ScoreEvidence,
    ScoreStatus,
)

NOT_SCORED = "This experiment hasn't been scored yet."
NO_ANSWER = "This answer has no scores in that pass."


def check_kind(extra: dict[str, object]) -> str:
    if extra.get("judged"):
        return "judge"
    if extra.get("code"):
        return "code"
    return "rule"


class EvidenceService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._engine = EngineRepository(session)
        self._scores = ScoreRepository(session)
        self._evaluators = EvaluatorRepository(session)
        self._labels = LabelService(session, settings)

    async def evidence(
        self, project_id: uuid.UUID, experiment_id: uuid.UUID, test_case_run_id: uuid.UUID, run_id: uuid.UUID | None
    ) -> EvidenceOut:
        if await self._engine.experiment(experiment_id, project_id) is None:
            raise NotFound("This experiment doesn't exist in this project.")
        runs = await self._scores.runs(experiment_id)
        run = next((r for r in runs if r.id == run_id), None) if run_id else None
        run = run or next((r for r in runs if r.status is EvaluationRunStatus.COMPLETED), None)
        if run is None:
            raise NotFound(NOT_SCORED)
        every = await self._scores.scores(experiment_id, run.id)
        mine = [s for s in every if s.test_case_run_id == test_case_run_id]
        if not mine:
            raise NotFound(NO_ANSWER)
        scored: Counter[str] = Counter(s.evaluator_name for s in every if s.status == ScoreStatus.SCORED)
        unscored: Counter[str] = Counter(s.evaluator_name for s in every if s.status != ScoreStatus.SCORED)
        agreements: dict[str, AgreementOut] = {
            a.evaluator_name: a for a in await self._labels.agreement(project_id, experiment_id, run.id)
        }
        catalog = gallery()
        found = []
        for score in sorted(mine, key=lambda s: s.evaluator_name):
            kind = check_kind(score.extra)
            entry = catalog.judges.get(score.evaluator_name.removeprefix("g_eval_"))
            limits = catalog.generic_limits[kind]
            if entry is not None and kind == "judge":
                limits = entry.limits
            elif kind == "rule" and score.evaluator_name in RULE_INFO:
                limits = f"{RULE_INFO[score.evaluator_name]['description']} {limits}"
            found.append(
                ScoreEvidence(
                    evaluator_name=score.evaluator_name,
                    kind=kind,
                    value=score.value,
                    passed=score.passed,
                    status=ScoreStatus(score.status),
                    reason=score.reason,
                    cached=bool(score.extra.get("cached")),
                    answers_scored=scored[score.evaluator_name],
                    answers_unscored=unscored[score.evaluator_name],
                    limits=limits,
                    agreement=agreements.get(score.evaluator_name),
                    agreement_note=None if score.evaluator_name in agreements or kind != "judge" else NOT_MEASURED,
                    reference_used=bool(score.extra.get("reference_used")),
                    prompt_seen=bool(score.extra.get("prompt_seen")),
                    combined=bool(score.extra.get("combined")),
                    usage=score.extra.get("usage"),
                )
            )
        return EvidenceOut(test_case_run_id=test_case_run_id, evaluation_run_id=run.id, scores=found)
