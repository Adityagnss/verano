"""The judge cache key changes with anything the judge sees or is told; the recent-results layer evicts the oldest."""

from app.modules.evaluation.judge_cache import CachedResult, RecentResults, cache_key


def key(**changes: object) -> str:
    base: dict[str, object] = {
        "evaluator_name": "g_eval_tone",
        "config": {"criteria": "Polite.", "kind": "deepeval"},
        "threshold": 0.5,
        "judge_model": "openai/gpt-x",
        "inputs": {"ticket": "hi", "lang": "en"},
        "output": "Hello!",
        "expected": None,
        "rubric": None,
        "context": [],
    }
    return cache_key(**(base | changes))  # type: ignore[arg-type]


def test_the_key_is_stable_whatever_the_order_of_the_dictionaries() -> None:
    assert key() == key(inputs={"lang": "en", "ticket": "hi"}, config={"kind": "deepeval", "criteria": "Polite."})
    assert len(key()) == 64


def test_anything_that_changes_what_the_judge_says_changes_the_key() -> None:
    seen = {
        key(),
        key(output="Hello"),
        key(judge_model="openai/gpt-y"),
        key(threshold=0.6),
        key(config={"criteria": "Very polite.", "kind": "deepeval"}),
        key(context=["a chunk"]),
        key(expected="Hello!"),
        key(evaluator_name="g_eval_other"),
    }
    assert len(seen) == 8


def test_the_recent_layer_drops_the_least_recently_used() -> None:
    recent = RecentResults(2)
    one, two, three = (CachedResult(0.1 * n, True, str(n)) for n in (1, 2, 3))
    recent.put("a", one)
    recent.put("b", two)
    assert recent.get("a") == one  # a is now the most recent
    recent.put("c", three)
    assert recent.get("b") is None
    assert recent.get("a") == one
    assert recent.get("c") == three
    assert len(recent) == 2
