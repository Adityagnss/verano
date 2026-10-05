"""Unit tests for the configuration fingerprint: what changes it and what must not."""

import uuid
from copy import deepcopy
from decimal import Decimal
from typing import Any

import pytest

from app.modules.engine.fingerprint import config_hash, model_settings
from app.modules.engine.models import Experiment
from app.modules.engine.schemas import ExperimentOrigin, ExperimentStatus, SplitScope

pytestmark = pytest.mark.unit

PROMPT, DATASET, EVALUATORS = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
GOOD, OTHER = str(uuid.uuid4()), str(uuid.uuid4())


def profile(profile_id: str, name: str, parameters: list[str]) -> dict[str, Any]:
    return {
        "id": profile_id,
        "provider": "mock",
        "model_name": name,
        "display_name": name,
        "parameters": {p: {} for p in parameters},
    }


def make(**changes: Any) -> Experiment:
    config: dict[str, Any] = {
        "models": [
            {"model_profile_id": GOOD, "display_name": "good", "runs": 2, "params": {"temperature": 0.0, "seed": 42}},
            {"model_profile_id": OTHER, "display_name": "other", "runs": 1, "params": {"temperature": 0.0}},
        ],
        "judge": {"credential_id": str(uuid.uuid4()), "model": "judge-1"},
    }
    snapshot = {
        "profiles": [profile(GOOD, "good", ["temperature", "seed"]), profile(OTHER, "other", ["temperature"])],
        "libraries": {"litellm": "1.0"},
    }
    values: dict[str, Any] = {
        "name": "A",
        "status": ExperimentStatus.COMPLETED,
        "origin": ExperimentOrigin.MANUAL,
        "prompt_version_id": PROMPT,
        "dataset_version_id": DATASET,
        "evaluator_set_version_id": EVALUATORS,
        "split_scope": SplitScope.ALL,
        "config": config,
        "snapshot": snapshot,
        "budget_cap": None,
    }
    values.update(changes)
    return Experiment(**values)


def test_the_same_setup_has_the_same_fingerprint_whatever_the_name_budget_or_model_order() -> None:
    base = make()
    config = deepcopy(base.config)
    config["models"].reverse()
    same = make(name="Another name", budget_cap=Decimal("5"), origin=ExperimentOrigin.OPTIMIZATION, config=config)
    assert config_hash(base) == config_hash(same)
    assert len(config_hash(base)) == 64


def test_numbers_written_differently_are_the_same_setting() -> None:
    config = deepcopy(make().config)
    config["models"][0]["params"] = {"temperature": 0, "seed": 42.0}
    assert config_hash(make(config=config)) == config_hash(make())


def test_a_setting_the_model_ignores_does_not_change_the_fingerprint() -> None:
    config = deepcopy(make().config)
    config["models"][1]["params"] = {"temperature": 0.0, "seed": 7, "stop": ["END"]}
    ignored = make(config=config)
    assert config_hash(ignored) == config_hash(make())
    assert model_settings(ignored)[1].ignored_params == ["seed", "stop"]


@pytest.mark.parametrize(
    "change", ["temperature", "seed", "runs", "model", "judge", "prompt", "dataset", "split", "evaluators"]
)
def test_every_real_difference_changes_the_fingerprint(change: str) -> None:
    config = deepcopy(make().config)
    snapshot = deepcopy(make().snapshot)
    values: dict[str, Any] = {}
    if change == "temperature":
        config["models"][0]["params"]["temperature"] = 0.7
    elif change == "seed":
        config["models"][0]["params"]["seed"] = 43
    elif change == "runs":
        config["models"][0]["runs"] = 3
    elif change == "model":
        snapshot["profiles"][0]["model_name"] = "good-2"
    elif change == "judge":
        config["judge"]["model"] = "judge-2"
    elif change == "prompt":
        values["prompt_version_id"] = uuid.uuid4()
    elif change == "dataset":
        values["dataset_version_id"] = uuid.uuid4()
    elif change == "split":
        values["split_scope"] = SplitScope.HOLDOUT
    else:
        values["evaluator_set_version_id"] = uuid.uuid4()
    assert config_hash(make(config=config, snapshot=snapshot, **values)) != config_hash(make())


def test_no_judge_is_a_setup_of_its_own() -> None:
    config = deepcopy(make().config)
    config["judge"] = None
    assert config_hash(make(config=config)) != config_hash(make())
