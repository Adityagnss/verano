"""Unit tests for the Eval Generator's pure logic and the dataset split."""

import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from app.core.datafiles import load_yaml
from app.modules.datasets.domain import SplitCandidate, assign_splits
from app.modules.datasets.schemas import ItemSource, Split
from app.modules.generator.domain import (
    EvaluatorCatalog,
    GenerationCatalog,
    answer_label,
    missing_labels,
    near_duplicates,
    plan_targets,
    select_evaluators,
    suggest_generator,
)
from app.modules.generator.plugins.embedders import LexicalEmbedder
from app.modules.generator.schemas import CaseCategory, TaskSpec
from app.modules.registry.schemas import ModelProfileOut, PriceSource

pytestmark = pytest.mark.unit

APP = Path(__file__).resolve().parents[3] / "app/modules"
CATEGORIES = load_yaml(APP / "generator/config/generation.yaml", GenerationCatalog)
EVALUATORS = load_yaml(APP / "evaluation/config/catalog.yaml", EvaluatorCatalog)
SPEC = TaskSpec(
    task_type="classification",
    goal="Classify tickets",
    input_variables=["ticket"],
    output_format="single_label",
    allowed_outputs=["billing", "shipping"],
    constraints=["one word"],
)


def test_targets_fill_only_the_gaps() -> None:
    assert plan_targets(CATEGORIES, 100, {}, {}) == {
        "happy_path": 40,
        "edge_case": 25,
        "tricky": 15,
        "format_stress": 10,
        "adversarial": 10,
    }
    targets = plan_targets(CATEGORIES, 100, {"billing": 30, "edge_case": 5}, {"tricky": 15})
    assert targets == {"happy_path": 10, "edge_case": 20, "tricky": 0, "format_stress": 10, "adversarial": 10}
    assert plan_targets(CATEGORIES, 20, {"happy_path": 500}, {})[CaseCategory.HAPPY_PATH] == 0


def test_near_duplicates_keep_real_rows_and_drop_repeats() -> None:
    embed = LexicalEmbedder().embed
    kept = embed(["My card was charged twice"])
    new = embed(["my card was charged twice!", "Where is my parcel?", "where is my parcel ?"])
    assert near_duplicates(kept, new, 0.92) == [0, 2]


def test_split_is_stratified_and_holds_out_golden_rows() -> None:
    items = [SplitCandidate(uuid.uuid4(), "happy_path", ItemSource.GENERATED) for _ in range(67)]
    items += [SplitCandidate(uuid.uuid4(), "edge_case", ItemSource.GENERATED) for _ in range(30)]
    items += [SplitCandidate(uuid.uuid4(), "happy_path", ItemSource.GOLDEN) for _ in range(3)]
    splits = assign_splits(items, 0.3, seed=7)
    assert sum(split is Split.HOLDOUT for split in splits.values()) == 30
    edge = [splits[i.id] for i in items if i.category == "edge_case"]
    assert edge.count(Split.HOLDOUT) == 9
    assert any(splits[i.id] is Split.HOLDOUT for i in items if i.source is ItemSource.GOLDEN)
    assert assign_splits(items, 0.3, seed=7) == splits


def test_labels_evaluators_and_generator_choice() -> None:
    assert answer_label(" Billing. ", ["billing", "shipping"]) == "billing"
    assert answer_label("refund", ["billing"]) is None
    assert missing_labels(SPEC, ["billing", None]) == ["shipping"]
    chosen = select_evaluators(SPEC, EVALUATORS)
    assert [c.name for c in chosen] == ["exact_match", "allowed_values", "constraints"]
    assert chosen[1].config["allowed_outputs"] == ["billing", "shipping"]
    assert chosen[2].config["constraints"] == ["one word"]

    def profile(name: str, price: str) -> ModelProfileOut:
        return ModelProfileOut(
            id=uuid.uuid4(),
            credential_id=uuid.uuid4(),
            provider="mock",
            model_name=name,
            display_name=name,
            litellm_model=name,
            context_window=None,
            max_output_tokens=None,
            parameters={},
            supports_json_mode=True,
            supports_system_prompt=True,
            input_price_per_mtok=Decimal(price),
            output_price_per_mtok=Decimal(price),
            price_source=PriceSource.PROVIDER,
            price_known=True,
            is_selected=True,
        )

    best = suggest_generator([profile("small", "0.6"), profile("large", "15")])
    assert best is not None
    assert best.model_name == "large"
    local = [profile("llama3.2:3b", "0"), profile("qwen2.5:14b", "0")]
    best = suggest_generator(local)
    assert best is not None
    assert best.model_name == "qwen2.5:14b"
