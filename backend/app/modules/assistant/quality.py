"""
Mean quality of an experiment's latest scoring pass, over all its cases or only those in
one split (optimize / holdout), so candidates and the current prompt are compared on
exactly the same cases.
"""

from statistics import mean

from app.modules.datasets.schemas import Split
from app.modules.datasets.service import DatasetService
from app.modules.engine.models import Experiment
from app.modules.evaluation.results import ResultsService


async def quality(
    results: ResultsService, datasets: DatasetService, experiment: Experiment, split: Split | None = None
) -> float | None:
    outcomes = await results.outcomes(experiment)
    if split is not None:
        items = await datasets.items(experiment.dataset_version_id, ids=[o.dataset_item_id for o in outcomes])
        keep = {item.id for item in items if item.split is split}
        outcomes = [o for o in outcomes if o.dataset_item_id in keep]
    return mean(o.quality for o in outcomes) if outcomes else None
