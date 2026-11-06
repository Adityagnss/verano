"""Unit tests for the experiment lifecycle transition table."""

import itertools

import pytest

from app.core.errors import InvalidTransition
from app.modules.engine.domain import TERMINAL, TRANSITIONS, ensure_transition
from app.modules.engine.schemas import ExperimentStatus as S

pytestmark = [pytest.mark.unit, pytest.mark.engine]

LEGAL = {
    (S.DRAFT, S.PLANNED),
    (S.PLANNED, S.RUNNING),
    (S.PLANNED, S.CANCELLED),
    (S.RUNNING, S.EVALUATING),
    (S.RUNNING, S.PAUSED),
    (S.RUNNING, S.CANCELLED),
    (S.RUNNING, S.FAILED),
    (S.PAUSED, S.RUNNING),
    (S.PAUSED, S.CANCELLED),
    (S.EVALUATING, S.COMPLETED),
    (S.EVALUATING, S.CANCELLED),
    (S.EVALUATING, S.FAILED),
}


@pytest.mark.parametrize(("current", "target"), list(itertools.product(S, S)))
def test_exactly_the_documented_transitions_are_allowed(current: S, target: S) -> None:
    if (current, target) in LEGAL:
        ensure_transition(current, target)
    else:
        with pytest.raises(InvalidTransition):
            ensure_transition(current, target)


def test_every_status_is_in_the_table_and_terminal_states_are_final() -> None:
    assert set(TRANSITIONS) == set(S)
    assert {S.COMPLETED, S.CANCELLED, S.FAILED} == TERMINAL
