"""Unit tests for core foundations whose failure would silently corrupt behavior."""

import pytest
from jinja2.exceptions import SecurityError, UndefinedError

from app.core.ids import deterministic_id, uuid7
from app.core.templates import render_string

pytestmark = pytest.mark.unit


def test_uuid7_ids_sort_in_creation_order() -> None:
    ids = [uuid7() for _ in range(10_000)]
    assert {i.version for i in ids} == {7}
    assert sorted(ids) == ids
    assert len(set(ids)) == len(ids)


def test_deterministic_ids_are_stable_and_distinguish_every_part() -> None:
    assert deterministic_id("exp", "item", "model", 1) == deterministic_id("exp", "item", "model", 1)
    assert deterministic_id("exp", "item", "model", 1) != deterministic_id("exp", "item", "model", 2)
    assert deterministic_id("a", "bc") != deterministic_id("ab", "c")


@pytest.mark.parametrize(
    "template",
    [
        "{{ ''.__class__.__mro__[1].__subclasses__() }}",
        "{{ cycler.__init__.__globals__.os.popen('id').read() }}",
        "{{ ticket.__class__.__base__.__subclasses__() }}",
    ],
)
def test_sandboxed_templates_cannot_reach_python_internals(template: str) -> None:
    with pytest.raises((SecurityError, UndefinedError)):
        render_string(template, ticket="hello")


def test_sandboxed_templates_fail_loudly_on_missing_variables() -> None:
    assert render_string("Ticket: {{ ticket }}", ticket="refund please") == "Ticket: refund please"
    with pytest.raises(UndefinedError):
        render_string("Ticket: {{ tickt }}", ticket="refund please")
