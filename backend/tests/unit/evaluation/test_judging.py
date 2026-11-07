"""What a judge is told (ADR 0038): the prompt shown, the reference rule, cache extras, the combined call's prompt and
reply reading, and the rubric helpers. Pure functions, no model."""

from typing import Any

from app.modules.evaluation.domain import EvalCase
from app.modules.evaluation.judging import (
    REFERENCE_NOTE,
    REFERENCE_STEP,
    CheckVerdict,
    CombinedCheck,
    CombinedVerdicts,
    RubricIssue,
    RubricReview,
    cache_extras,
    clean_criteria,
    combined_prompt,
    input_for_judge,
    local_issues,
    prompt_text,
    read_combined,
    reference_of,
    share_of,
    trusted_issues,
    with_reference_note,
)
from app.modules.generator.schemas import OutputFormat, TaskSpec, TaskType

SPEC = TaskSpec(
    task_type=TaskType.GENERATION, goal="Reply", input_variables=["q"], output_format=OutputFormat.FREE_TEXT
)


def case(**extra: Any) -> EvalCase:
    base: dict[str, Any] = {
        "inputs": {"q": "hi"},
        "output": "hello",
        "expected": "greeting",
        "rubric": None,
        "task_spec": SPEC,
        "prompt": "Be polite.",
    }
    return EvalCase(**{**base, **extra})


def test_prompt_text_joins_messages_cuts_long_ones_and_is_off_at_zero() -> None:
    assert prompt_text("Sys", "User {{q}}", 1000) == "System message:\nSys\n\nUser message:\nUser {{q}}"
    assert prompt_text(None, "only user", 1000) == "User message:\nonly user"
    assert prompt_text("  ", None, 1000) is None
    assert prompt_text("Sys", None, 0) is None
    cut = prompt_text("x" * 100, None, 40)
    assert cut is not None
    assert "left out because it is long" in cut


def test_the_judge_sees_the_prompt_unless_the_check_or_the_case_leaves_it_out() -> None:
    assert "Be polite." in input_for_judge({}, case())
    assert "Be polite." not in input_for_judge({"include_prompt": False}, case())
    assert "Be polite." not in input_for_judge({}, case(prompt=None))
    assert "q: hi" in input_for_judge({}, case())


def test_the_expected_answer_is_the_reference_unless_switched_off() -> None:
    assert reference_of({}, case()) == "greeting"
    assert reference_of({"use_reference": False}, case()) is None
    assert reference_of({}, case(reference_on=False)) is None
    assert reference_of({}, case(expected=None)) is None
    # a check that needs the expected answer always gets it
    assert reference_of({"requires": "expected", "use_reference": False}, case(reference_on=False)) == "greeting"


def test_the_reference_sentence_joins_criteria_or_becomes_a_step() -> None:
    assert with_reference_note("Is polite", [], False) == ("Is polite", [])
    criteria, steps = with_reference_note("Is polite", [], True)
    assert criteria == f"Is polite. {REFERENCE_NOTE}"
    assert steps == []
    assert with_reference_note("Ends here.", [], True)[0] == f"Ends here. {REFERENCE_NOTE}"
    assert with_reference_note(None, [], True) == (REFERENCE_NOTE, [])
    assert with_reference_note("c", ["one"], True) == ("c", ["one", REFERENCE_STEP])


def test_cache_extras_change_with_the_prompt_and_the_reference_and_are_empty_when_neither_applies() -> None:
    plain = case(prompt=None, expected=None)
    assert cache_extras({}, plain) == {}
    with_prompt = cache_extras({}, case())
    assert with_prompt == {"prompt": "Be polite.", "reference": True}
    assert cache_extras({"use_reference": False}, case()) != with_prompt
    assert cache_extras({}, case(prompt="Be rude.")) != with_prompt
    assert cache_extras({"include_prompt": False}, case()) == {"reference": True}


def checks() -> list[CombinedCheck]:
    return [
        CombinedCheck("tone", 0.5, "Polite tone", [], {}),
        CombinedCheck("facts", 0.7, None, ["Look for facts", "Fail invented ones"], {"use_reference": False}),
    ]


def test_the_combined_prompt_holds_every_check_in_its_own_words_and_the_shared_context_once() -> None:
    text = combined_prompt(checks(), case(), "hello")
    assert text.count("Be polite.") == 1
    assert text.count("The answer to judge:\nhello") == 1
    assert 'Check 1, named "tone"' in text
    assert "Criteria: Polite tone" in text
    assert 'Check 2, named "facts"' in text
    assert "1. Look for facts" in text
    assert text.count("Reference answer") == 1
    assert REFERENCE_NOTE in text  # tone uses the reference; facts opted out
    assert REFERENCE_STEP not in text


def test_the_combined_prompt_shows_context_only_to_checks_that_need_it() -> None:
    needs = [CombinedCheck("grounded", 0.5, "Uses context", [], {"requires": "context"})]
    assert "Context the answer may rely on" in combined_prompt(needs, case(context=["fact A"]), "a")
    assert "Context the answer" not in combined_prompt(checks(), case(context=["fact A"]), "a")


def test_reading_the_combined_reply_scores_good_entries_and_returns_none_for_the_rest() -> None:
    reply = CombinedVerdicts(
        checks=[
            CheckVerdict(name="tone", score=8, reason="warm"),
            CheckVerdict(name="facts", score=11, reason="out of range"),
            CheckVerdict(name="extra", score=5),
        ]
    )
    found = read_combined(checks(), reply)
    tone = found["tone"]
    assert tone is not None
    assert tone.value == 0.8
    assert tone.passed
    assert tone.reason == "warm"
    assert tone.metadata["combined"] is True
    assert found["facts"] is None  # outside 0 to 10: scored again alone
    assert "extra" not in found


def test_a_repeated_or_missing_check_in_the_reply_is_not_guessed() -> None:
    twice = CombinedVerdicts(checks=[CheckVerdict(name="tone", score=9), CheckVerdict(name="tone", score=1)])
    found = read_combined(checks(), twice)
    assert found == {"tone": None, "facts": None}
    blank = read_combined(checks(), CombinedVerdicts(checks=[CheckVerdict(name=" tone ", score=3, reason="  ")]))
    tone = blank["tone"]
    assert tone is not None
    assert not tone.passed
    assert tone.reason == "The judge gave no reason."


def test_a_call_cost_is_shared_equally() -> None:
    assert share_of(0.3, 3) == 0.3 / 3
    assert share_of(5, 0) == 0.0


def test_criteria_are_trimmed_deduplicated_and_cut() -> None:
    cleaned = clean_criteria(["  - Be brief ", "be BRIEF", "1. Cite sources", "", "x" * 50], 20)
    assert cleaned == ["Be brief", "Cite sources", "x" * 20]


def test_local_rubric_issues_find_size_repeats_long_and_vague_criteria() -> None:

    def kinds(found: list[Any]) -> list[str]:
        return sorted(i.kind for i in found)

    assert kinds(local_issues(["Mentions the refund window of 30 days"], 3, 8, 200)) == ["size"]
    many = [f"Mentions fact number {n} from the context" for n in range(9)]
    assert kinds(local_issues(many, 3, 8, 200)) == ["size"]
    repeated = local_issues(["Cite the order id", "cite the order id!", "Be polite to the customer today"], 3, 8, 200)
    assert [(i.kind, i.criterion) for i in repeated] == [("duplicate", 2)]
    vague = local_issues(["Be good", "Cites the order id", "Mentions the 30 day refund window"], 3, 8, 200)
    assert [(i.kind, i.criterion) for i in vague] == [("vague", 1)]
    assert vague[0].suggestion
    long = local_issues(["Mentions the order id " * 5, "b b b b b b", "c c c c c c"], 3, 8, 30)
    assert ("size", 1) in [(i.kind, i.criterion) for i in long]


def test_only_sensible_judge_issues_are_trusted() -> None:
    reply = RubricReview(
        issues=[
            RubricIssue(kind="vague", criterion=2, detail="d"),
            RubricIssue(kind="made_up", criterion=1, detail="d"),
            RubricIssue(kind="inconsistent", criterion=9, detail="d"),
        ]
    )
    kept = trusted_issues(reply, 3)
    assert [(i.kind, i.criterion) for i in kept] == [("vague", 2), ("inconsistent", None)]
