"""
The cost preview shown before generating (DEVELOPMENT.md C1: show cost before spending):
how many cases and answers a run would produce, how many model calls that takes, and the
estimated cost at the generator model's price. Read-only: it never creates a draft.
"""

import uuid
from decimal import Decimal
from pathlib import Path

from app.core.config import Settings
from app.core.datafiles import load_yaml
from app.core.errors import Conflict
from app.modules.datasets.schemas import ItemSource
from app.modules.datasets.service import DatasetService
from app.modules.gateway.domain import compute_cost
from app.modules.generator.domain import GenerationCatalog, estimate_calls, plan_targets
from app.modules.generator.models import TaskSpecRecord
from app.modules.generator.schemas import GenerationEstimate, GenerationRequest
from app.modules.registry.service import RegistryService

NO_GENERATOR = (
    "This Task Spec has no model to write test cases with: it was written by hand (for example with "
    "`verano push`). Draft the Task Spec on the Tests step and choose a model, or use only your own test cases."
)
CATEGORIES = load_yaml(Path(__file__).parent / "config" / "generation.yaml", GenerationCatalog)
NOTHING = GenerationEstimate(
    cases_to_generate=0,
    answers_to_draft=0,
    calls=0,
    input_tokens=0,
    output_tokens=0,
    cost=Decimal(0),
    price_known=True,
)


async def estimate_generation(
    settings: Settings,
    registry: RegistryService,
    datasets: DatasetService,
    project_id: uuid.UUID,
    row: TaskSpecRecord,
    body: GenerationRequest,
) -> GenerationEstimate:
    if body.golden_only:
        return NOTHING
    if row.generator_credential_id is None or row.generator_model is None:
        raise Conflict(NO_GENERATOR)
    draft = await datasets.find_draft(project_id)
    existing = await datasets.items(draft.id) if draft else []
    items = [item for item in existing if item.source is not ItemSource.GENERATED]
    real: dict[str, int] = {}
    for item in items:
        real[item.category] = real.get(item.category, 0) + 1
    targets = plan_targets(CATEGORIES, body.target_size or settings.generator_default_size, real, {})
    answers = sum(targets.values())
    sizes = estimate_calls(targets, answers, settings.generator_batch_size, settings.generator_answer_batch_size)
    profile = (await registry.call_target(project_id, row.generator_credential_id, row.generator_model)).profile
    cost = compute_cost(
        sizes.input_tokens, sizes.output_tokens, profile.input_price_per_mtok, profile.output_price_per_mtok
    )
    return GenerationEstimate(
        confirm_above=settings.generator_confirm_cost,
        needs_confirmation=cost is None or cost > settings.generator_confirm_cost,
        cases_to_generate=sum(targets.values()),
        answers_to_draft=answers,
        calls=sizes.calls,
        input_tokens=sizes.input_tokens,
        output_tokens=sizes.output_tokens,
        cost=cost,
        price_known=cost is not None,
    )
