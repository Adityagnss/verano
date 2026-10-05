"""Unit tests for sampling settings: what is refused, how equal settings are written the same, per-run seeds."""

import uuid
from typing import Any

import pytest
from pydantic import ValidationError

from app.modules.engine.domain import param_set_key, plan_matrix
from app.modules.engine.sampling import MAX_SEED, normalize_params, run_params

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "params",
    [
        {"temprature": 0.2},
        {"temperature": True},
        {"temperature": "0.2"},
        {"temperature": float("nan")},
        {"temperature": float("inf")},
        {"temperature": 2.5},
        {"top_p": 1.1},
        {"top_k": 0},
        {"seed": -1},
        {"seed": 1.5},
        {"seed": False},
        {"seed": MAX_SEED + 1},
        {"max_tokens": 0},
        {"frequency_penalty": 3},
        {"stop": "END"},
        {"stop": [1]},
        {"stop": ["a", "b", "c", "d", "e"]},
        {"stop": ["x" * 101]},
    ],
)
def test_bad_settings_are_refused(params: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        normalize_params(params)


def test_equal_settings_are_written_the_same_way() -> None:
    assert normalize_params({"temperature": 0, "seed": 7.0}) == {"temperature": 0.0, "seed": 7}
    assert normalize_params({"temperature": None, "stop": []}) == {}
    assert normalize_params({"stop": ["b", "", "a", "b"]}) == {"stop": ["a", "b"]}
    assert param_set_key(normalize_params({"temperature": 0})) == param_set_key(normalize_params({"temperature": 0.0}))
    assert normalize_params({"stop": ["\n\n"]}) == {"stop": ["\n\n"]}


def test_each_repeated_run_gets_the_next_seed_and_the_settings_key_stays_put() -> None:
    assert run_params({"temperature": 0.0}, 3) == {"temperature": 0.0}
    assert [run_params({"seed": 42}, run)["seed"] for run in (1, 2, 3)] == [42, 43, 44]
    experiment, item, model = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    planned = plan_matrix(experiment, [item], [(model, 3, {"seed": 42})])
    assert [call.params["seed"] for call in planned] == [42, 43, 44]
    assert len({call.param_set_key for call in planned}) == 1
    assert planned[0].param_set_key == param_set_key({"seed": 42})
    last = plan_matrix(experiment, [item], [(model, 5, {"seed": MAX_SEED})])[-1]
    assert last.params["seed"] == 2**31 - 1
