"""Unit tests for the matrix planner: deterministic ids and the call count."""

import uuid

import pytest

from app.modules.engine.domain import param_set_key, plan_matrix, run_id

pytestmark = pytest.mark.unit


def test_every_cell_has_a_stable_unique_id() -> None:
    experiment, items = uuid.uuid4(), [uuid.uuid4() for _ in range(3)]
    models = [(uuid.uuid4(), 2, {"temperature": 0.2}), (uuid.uuid4(), 1, {})]
    planned = plan_matrix(experiment, items, models)
    assert len(planned) == 3 * 2 + 3 * 1
    assert len({call.id for call in planned}) == len(planned)
    assert [c.id for c in plan_matrix(experiment, items, models)] == [c.id for c in planned]
    key = param_set_key({"temperature": 0.2})
    assert planned[0].id == run_id(experiment, items[0], models[0][0], key, 1)
    assert param_set_key({"a": 1, "b": 2}) == param_set_key({"b": 2, "a": 1})
