"""
The DeepEval adapter (ADR 0003): LLM-judge metrics run through our gateway, never directly.

`GatewayJudge` is DeepEval's custom-model class backed by `GatewayService`, so every judge
call is rate-limited, retried, costed and recorded like any other call (purpose `judge`),
and structured replies go through the gateway's JSON repair. `judge` runs G-Eval for one
case with the evaluator's criteria, or its own evaluation steps when it has them; "{rubric}" means
the case's own rubric. The G-Eval
score is already normalized to 0.0-1.0. Telemetry is switched off before DeepEval loads.
"""

import json
import os
from typing import Any

from pydantic import BaseModel

from app.modules.evaluation.domain import EvalCase, Score, score
from app.modules.evaluation.judging import input_for_judge, reference_of, with_reference_note
from app.modules.gateway.schemas import CallContext, CallPurpose, Message
from app.modules.gateway.service import GatewayService
from app.modules.registry.schemas import CallTarget

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
os.environ.setdefault("DEEPEVAL_UPDATE_WARNING_OPT_IN", "NO")

RUBRIC = "{rubric}"


def _judge_class() -> type:
    from deepeval.models import DeepEvalBaseLLM

    class GatewayJudge(DeepEvalBaseLLM):  # type: ignore[no-untyped-call]
        def __init__(self, gateway: GatewayService, target: CallTarget, context: CallContext) -> None:
            self._gateway, self._target, self._context = gateway, target, context
            super().__init__(target.profile.model_name)

        def load_model(self, *args: Any, **kwargs: Any) -> "GatewayJudge":
            return self

        def generate(self, *args: Any, **kwargs: Any) -> str:
            raise NotImplementedError("Verano runs judges asynchronously only.")

        async def a_generate(self, prompt: str, schema: type[BaseModel] | None = None, **_: Any) -> Any:
            messages = [Message(role="user", content=prompt)]
            if schema is not None:
                return await self._gateway.complete_json_target(
                    self._target, messages, schema, CallPurpose.JUDGE, self._context
                )
            result = await self._gateway.complete_target(self._target, messages, {}, CallPurpose.JUDGE, self._context)
            return result.text

        def get_model_name(self, *args: Any, **kwargs: Any) -> str:
            return str(self._target.profile.display_name)

    return GatewayJudge


def steps_of(config: dict[str, Any]) -> list[str]:
    return [str(step).strip() for step in config.get("evaluation_steps") or [] if str(step).strip()]


def _rubric_text(case: EvalCase) -> str | None:
    return "A good answer meets every one of these criteria: " + "; ".join(case.rubric) if case.rubric else None


def instructions_for(config: dict[str, Any], case: EvalCase) -> tuple[str | None, list[str]] | None:
    """What the judge is asked about this case: (criteria, steps), or None when the check does not apply
    (it uses the case's own rubric and the case has none). Steps, when given, replace the criteria, and a step
    that is exactly "{rubric}" stands for the case's rubric."""
    needs = {part.strip() for part in str(config.get("requires") or "").split(",")}
    if "context" in needs and not case.context:
        return None
    if "tool_calls" in needs and not case.tool_calls:
        return None
    if "expected" in needs and not case.expected:
        return None
    steps = steps_of(config)
    if steps:
        if RUBRIC not in steps:
            return None, steps
        rubric = _rubric_text(case)
        return (None, [rubric if step == RUBRIC else step for step in steps]) if rubric else None
    criteria = str(config.get("criteria") or "").strip()
    if criteria == RUBRIC:
        rubric = _rubric_text(case)
        return (rubric, []) if rubric else None
    return (criteria, []) if criteria else None


def _needs(config: dict[str, Any]) -> set[str]:
    return {part.strip() for part in str(config.get("requires") or "").split(",")}


def criteria_for(config: dict[str, Any], case: EvalCase) -> str | None:
    asked = instructions_for(config, case)
    return asked[0] if asked else None


def answer_text(config: dict[str, Any], case: EvalCase) -> str:
    """The answer the judge reads. A judge that looks at tool use also gets the tools the app called."""
    if not config.get("include_tool_calls") or not case.tool_calls:
        return case.output
    calls = "\n".join(
        f"- {call.get('name')}({json.dumps(call.get('arguments', {}), ensure_ascii=False)})" for call in case.tool_calls
    )
    return f"{case.output}\n\nTools the app called:\n{calls}"


async def judge(
    gateway: GatewayService,
    target: CallTarget,
    context: CallContext,
    name: str,
    config: dict[str, Any],
    threshold: float,
    case: EvalCase,
) -> Score | None:
    asked = instructions_for(config, case)
    if asked is None:
        return None
    criteria, steps = asked
    from deepeval.metrics import GEval
    from deepeval.test_case import LLMTestCase, SingleTurnParams

    reference = reference_of(config, case)
    criteria, steps = with_reference_note(criteria, steps, reference is not None and "expected" not in _needs(config))
    params = [SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT]
    if reference is not None:
        params.append(SingleTurnParams.EXPECTED_OUTPUT)
    if case.context:
        params.append(SingleTurnParams.CONTEXT)
    metric = GEval(
        name=name,
        criteria=criteria,
        evaluation_steps=steps or None,
        evaluation_params=params,
        model=_judge_class()(gateway, target, context),
        threshold=threshold,
        async_mode=True,
        verbose_mode=False,
    )
    test_case = LLMTestCase(
        input=input_for_judge(config, case),
        actual_output=answer_text(config, case),
        expected_output=reference,
        context=[str(item) for item in case.context] or None,
    )
    await metric.a_measure(test_case, _show_indicator=False)
    value = min(1.0, max(0.0, float(metric.score or 0.0)))
    return score(value, threshold, str(metric.reason or ""))
