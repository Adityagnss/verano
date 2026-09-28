"""
Evaluation background job: score a finished (or stopped) experiment with its evaluator
set. Scoring writes a new EvaluationRun each time, so a repeated delivery only adds a
duplicate pass; it never changes outputs or earlier scores.
"""

import uuid

from app.core.container import Container
from app.core.jobs import job
from app.modules.evaluation.schemas import EvaluationTrigger
from app.modules.evaluation.scoring import ScoringService


@job("evaluation.score_experiment", time_limit_setting="evaluation_timeout_s")
async def score_experiment(
    container: Container, experiment_id: str, trigger: str = "initial", evaluator_set_version_id: str | None = None
) -> None:
    async with container.database.sessions() as session:
        version = uuid.UUID(evaluator_set_version_id) if evaluator_set_version_id else None
        await ScoringService(session, container).score(uuid.UUID(experiment_id), EvaluationTrigger(trigger), version)
