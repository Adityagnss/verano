"""Unit tests for returned model ids: what counts as a change and what is only unknown."""

import uuid

import pytest

from app.modules.engine.provenance import ReturnedModel, changed_between, changed_within, known, summarize

pytestmark = pytest.mark.unit

A, B = uuid.uuid4(), uuid.uuid4()


def test_ids_are_grouped_per_model_with_the_most_used_first() -> None:
    found = summarize([(A, "v2", 1), (A, "v1", 5), (B, None, 3), (A, None, 2)])
    assert found[A] == [ReturnedModel("v1", 5), ReturnedModel(None, 2), ReturnedModel("v2", 1)]
    assert found[B] == [ReturnedModel(None, 3)]


def test_a_model_changed_only_when_it_reported_more_than_one_id() -> None:
    assert changed_within([ReturnedModel("v1", 4), ReturnedModel("v2", 1)])
    assert not changed_within([ReturnedModel("v1", 5)])
    assert not changed_within([ReturnedModel("v1", 5), ReturnedModel(None, 2)])
    assert not changed_within([])
    assert known([ReturnedModel("", 1), ReturnedModel("v1", 1)]) == {"v1"}


def test_between_experiments_both_sides_must_have_reported_and_differ() -> None:
    v1, v2 = [ReturnedModel("v1", 3)], [ReturnedModel("v2", 3)]
    assert changed_between(v1, v2)
    assert not changed_between(v1, [ReturnedModel("v1", 9)])
    assert not changed_between(v1, [ReturnedModel(None, 3)])
    assert not changed_between([], v2)
    assert changed_between(v1, [ReturnedModel("v1", 1), ReturnedModel("v2", 1)])
