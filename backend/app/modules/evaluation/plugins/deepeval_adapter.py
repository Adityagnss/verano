"""
The DeepEval adapter (ADR 0003): LLM-judge metrics run through our gateway, never directly.

`GatewayJudge` is DeepEval's custom-model class backed by `GatewayService`, so every judge
call is rate-limited, retried, costed and recorded like any other call (purpose `judge`),
and structured replies go through the gateway's JSON repair. `judge` runs G-Eval for one
case with the evaluator's criteria; "{rubric}" means the case's own rubric. The G-Eval
score is already normalized to 0.0-1.0. Telemetry is switched off before DeepEval loads.
"""

import os
from typing import Any

from pydantic import BaseModel

from app.modules.evaluation.domain import EvalCase, Score, score
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


def criteria_for(config: dict[str, Any], case: EvalCase) -> str | None:
    criteria = str(config.get("criteria") or "")
    if criteria == RUBRIC:
        return "A good answer meets every one of these criteria: " + "; ".join(case.rubric) if case.rubric else None
    return criteria or None


async def judge(
    gateway: GatewayService,
    target: CallTarget,
    context: CallContext,
    name: str,
    config: dict[str, Any],
    threshold: float,
    case: EvalCase,
) -> Score | None:
    criteria = criteria_for(config, case)
    if criteria is None:
        return None
    from deepeval.metrics import GEval
    from deepeval.test_case import LLMTestCase, SingleTurnParams

    params = [SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT]
    if case.expected is not None:
        params.append(SingleTurnParams.EXPECTED_OUTPUT)
    if case.context:
        params.append(SingleTurnParams.CONTEXT)
    metric = GEval(
        name=name,
        criteria=criteria,
        evaluation_params=params,
        model=_judge_class()(gateway, target, context),
        threshold=threshold,
        async_mode=True,
        verbose_mode=False,
    )
    test_case = LLMTestCase(
        input="\n".join(f"{key}: {value}" for key, value in case.inputs.items()),
        actual_output=case.output,
        expected_output=case.expected,
        context=[str(item) for item in case.context] or None,
    )
    await metric.a_measure(test_case, _show_indicator=False)
    value = min(1.0, max(0.0, float(metric.score or 0.0)))
    return score(value, threshold, str(metric.reason or ""))
