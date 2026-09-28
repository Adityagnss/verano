"""
Evaluation background job: score a finished (or stopped) experiment. Until scoring lands,
it only completes an experiment that is waiting to be scored.
"""

import uuid

from app.core.container import Container
from app.core.jobs import job
from app.core.security import utcnow
from app.modules.engine.schemas import ExperimentStatus
from app.modules.engine.service import ExperimentService


@job("evaluation.score_experiment", time_limit_setting="evaluation_timeout_s")
async def score_experiment(container: Container, experiment_id: str) -> None:
    async with container.database.sessions() as session:
        experiments = ExperimentService.from_container(session, container)
        experiment = await experiments.experiment_row_any(uuid.UUID(experiment_id))
        if experiment is not None and experiment.status is ExperimentStatus.EVALUATING:
            await experiments.transition(experiment, ExperimentStatus.COMPLETED, values={"completed_at": utcnow()})
            await session.commit()
