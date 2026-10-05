"""
Mean quality of an experiment's latest scoring pass, over all its cases or only those in
one split (optimize / holdout), so candidates and the current prompt are compared on
exactly the same cases. If any case in scope could not be judged the result is None: a
number computed on part of the cases is not something to prove an improvement with.
"""

from statistics import mean

from app.modules.datasets.schemas import Split
from app.modules.datasets.service import DatasetService
from app.modules.engine.models import Experiment
from app.modules.evaluation.comparisons import case_results
from app.modules.evaluation.results import ResultsService
from app.modules.evaluation.significance import CaseResult


async def quality(
    results: ResultsService, datasets: DatasetService, experiment: Experiment, split: Split | None = None
) -> float | None:
    outcomes = await results.outcomes(experiment)
    if split is not None:
        items = await datasets.items(experiment.dataset_version_id, ids=[o.dataset_item_id for o in outcomes])
        keep = {item.id for item in items if item.split is split}
        outcomes = [o for o in outcomes if o.dataset_item_id in keep]
    if not outcomes or any(not o.judged for o in outcomes):
        return None
    return mean(o.quality for o in outcomes)


async def split_results(
    results: ResultsService, datasets: DatasetService, experiment: Experiment, split: Split
) -> tuple[dict[str, CaseResult], bool]:
    """Per-case results of the latest scoring pass on one split, and whether every case in scope was judged
    (when not, nothing can be proven with them)."""
    outcomes = await results.outcomes(experiment)
    items = await datasets.items(experiment.dataset_version_id, ids=[o.dataset_item_id for o in outcomes])
    keep = {item.id for item in items if item.split is split}
    scoped = [o for o in outcomes if o.dataset_item_id in keep]
    return case_results(scoped), bool(scoped) and all(o.judged for o in scoped)
