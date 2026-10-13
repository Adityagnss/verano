"""Identical answers to identical inputs are judged once per check in a scoring pass; a failed call is not shared."""

import asyncio
from types import SimpleNamespace
from typing import Any

from app.modules.evaluation.domain import EvalCase, Score, Unscored
from app.modules.evaluation.scoring import ScoringService
from app.modules.generator.schemas import OutputFormat, TaskSpec, TaskType

SPEC = TaskSpec(
    task_type=TaskType.GENERATION, goal="Write a reply", input_variables=["q"], output_format=OutputFormat.FREE_TEXT
)


def case(output: str) -> EvalCase:
    return EvalCase(inputs={"q": "hi"}, output=output, expected=None, rubric=None, task_spec=SPEC)


def service(results: list[Score | Unscored]) -> tuple[ScoringService, list[str]]:
    calls: list[str] = []
    scoring = object.__new__(ScoringService)

    async def evaluate(config: Any, eval_case: EvalCase, *_: Any) -> Score | Unscored:
        calls.append(eval_case.output)
        await asyncio.sleep(0)
        return results[min(len(calls), len(results)) - 1]

    scoring._evaluate = evaluate  # type: ignore[method-assign,assignment]
    return scoring, calls


CONFIG = SimpleNamespace(evaluator_name="g_eval_x", config={"kind": "deepeval", "criteria": "c"}, threshold=0.5)


async def test_identical_answers_share_one_judge_call() -> None:
    scoring, calls = service([Score(1.0, True, "ok")])
    shared: dict[str, Any] = {}

    async def run(text: str) -> Score | Unscored | None:
        return await scoring._evaluate_once(CONFIG, case(text), object(), None, None, shared)  # type: ignore[arg-type]

    results = await asyncio.gather(run("same"), run("same"), run("other"))
    assert calls == ["same", "other"]
    assert results[0] is results[1]


async def test_a_failed_judge_call_is_not_shared() -> None:
    scoring, calls = service([Unscored("down"), Score(1.0, True, "ok")])
    shared: dict[str, Any] = {}

    async def run() -> Score | Unscored | None:
        return await scoring._evaluate_once(CONFIG, case("same"), object(), None, None, shared)  # type: ignore[arg-type]

    first, second = await asyncio.gather(run(), run())
    assert isinstance(first, Unscored)
    assert isinstance(second, Score)
    assert calls == ["same", "same"]
