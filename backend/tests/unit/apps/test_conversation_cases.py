"""Pure parts of conversation case generation (ADR 0039): which written cases are kept, the turn cap, and the
stopping condition reaching the simulated user."""

from app.core.templates import render_system_prompt
from app.modules.apps.case_schemas import GeneratedConversationCase
from app.modules.apps.cases import accept_cases, case_row, covered_keys
from app.modules.apps.conversation import case_turns
from app.modules.apps.simulator import PROMPTS


def written(goal: str = "Get a refund", opening: str = "Hi", **extra: object) -> GeneratedConversationCase:
    values = {"persona": "A customer", "goal": goal, "opening": opening, "stop_when": "Refund promised", **extra}
    return GeneratedConversationCase.model_validate(values)


def test_repeats_blanks_and_the_overflow_are_left_out_and_counted() -> None:
    cases = [
        written("Get a refund", "Hi"),
        written("  get   a REFUND ", "Another opening"),  # same goal in other words
        written("Cancel", "Hi"),  # same opening as the first
        written("Change address", "Move it", persona="   "),  # blank persona
        written("Track parcel", "Where?"),
        written("Update email", "New email"),
    ]
    rows, repeats, blank = accept_cases(cases, set(), want=2, turn_cap=8)
    assert [r["inputs"]["goal"] for r in rows] == ["Get a refund", "Track parcel"]
    assert (repeats, blank) == (2, 1)
    assert rows[0]["review_status"] == "draft"
    assert rows[0]["rubric"] == ["Refund promised"]


def test_cases_the_project_already_has_are_not_written_again() -> None:
    covered = covered_keys([{"goal": "Get a Refund", "opening": "x"}, {"other": 1}])
    rows, repeats, _ = accept_cases([written("get a refund", "new"), written("Other", "Different")], covered, 5, 8)
    assert len(rows) == 1
    assert repeats == 1


def test_turns_are_capped_by_the_server_and_a_case_may_ask_for_fewer() -> None:
    assert case_row(written(max_turns=50), 8)["inputs"]["max_turns"] == 8
    assert case_row(written(max_turns=3), 8)["inputs"]["max_turns"] == 3
    assert "max_turns" not in case_row(written(), 8)["inputs"]
    assert case_turns({"max_turns": 3}, 8) == 3
    assert case_turns({"max_turns": 30}, 8) == 8
    assert case_turns({"max_turns": 0}, 8) == 8
    assert case_turns({"max_turns": True}, 8) == 8
    assert case_turns({}, 8) == 8


def test_the_simulated_user_is_told_when_the_conversation_is_over() -> None:
    text = render_system_prompt(
        PROMPTS, "simulator.jinja", persona="p", goal="g", scenario=None, stop_when="Refund promised", done="DONE"
    )
    assert "The conversation is over when: Refund promised" in text
    plain = render_system_prompt(
        PROMPTS, "simulator.jinja", persona="p", goal="g", scenario=None, stop_when=None, done="DONE"
    )
    assert "over when" not in plain
