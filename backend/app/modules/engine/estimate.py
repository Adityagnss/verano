"""
The cost preview shown before an experiment starts (DEVELOPMENT.md 3.1): calls, estimated
tokens, generation cost per model and the judge cost of scoring. Prompt tokens come from
rendering every case; reply tokens from the model's max_tokens, or a typical reply size
when none is set. A model with an unknown price makes the total unknown, never $0.
Pure: the service supplies the prompt, cases and model profiles.
"""

import uuid
from decimal import Decimal
from typing import Any

from app.core.config import Settings
from app.core.tokens import estimate_tokens
from app.modules.engine.columns import Column, column_name
from app.modules.engine.schemas import ExperimentEstimate, ModelEstimate
from app.modules.gateway.domain import compute_cost
from app.modules.prompts.domain import render
from app.modules.prompts.schemas import PromptVersionOut
from app.modules.registry.schemas import ModelProfileOut

TYPICAL_REPLY_TOKENS = 200
JUDGE_OVERHEAD_TOKENS = 600
JUDGE_REPLY_TOKENS = 120


def _sum(values: list[Decimal | None]) -> Decimal | None:
    return None if any(value is None for value in values) else sum((v or Decimal(0) for v in values), Decimal(0))


def estimate_experiment(
    settings: Settings,
    prompt: PromptVersionOut,
    items: list[tuple[uuid.UUID, dict[str, Any]]],
    profiles: list[ModelProfileOut],
    columns: list[Column],
    judge: ModelProfileOut | None,
    judge_metrics: int,
    judge_checks: int | None = None,
) -> ExperimentEstimate:
    """`judge_metrics` is judge calls per answer; `judge_checks` the judged checks per answer (they differ when fast
    scoring shares one call between checks: fewer calls, the same instructions to read)."""
    units = judge_metrics if judge_checks is None else judge_checks
    chars = settings.token_estimate_chars_per_token
    prompt_tokens = sum(
        estimate_tokens((m.content for m in render(prompt.system_template, prompt.user_template, inputs)), 0, chars)
        for _, inputs in items
    )
    by_id = {profile.id: profile for profile in profiles}
    models, judge_in, judge_out, calls_total = [], 0, 0, 0
    for model in columns:
        profile = by_id[model.profile_id]
        reply = int(model.params.get("max_tokens") or TYPICAL_REPLY_TOKENS)
        calls = len(items) * model.runs
        input_tokens, output_tokens = prompt_tokens * model.runs, reply * calls
        cost = compute_cost(input_tokens, output_tokens, profile.input_price_per_mtok, profile.output_price_per_mtok)
        models.append(
            ModelEstimate(
                model_profile_id=model.column_id,
                display_name=column_name(profile.display_name, model.set_name),
                calls=calls,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
            )
        )
        calls_total += calls
        judge_in += (input_tokens + output_tokens) * judge_metrics + JUDGE_OVERHEAD_TOKENS * calls * units
        judge_out += JUDGE_REPLY_TOKENS * calls * judge_metrics
    generation = _sum([m.cost for m in models])
    judge_cost: Decimal | None = Decimal(0)
    if judge_metrics:
        judge_cost = (
            compute_cost(judge_in, judge_out, judge.input_price_per_mtok, judge.output_price_per_mtok)
            if judge
            else None
        )
    total = _sum([generation, judge_cost])
    return ExperimentEstimate(
        cases=len(items),
        calls=calls_total,
        input_tokens=sum(m.input_tokens for m in models),
        output_tokens=sum(m.output_tokens for m in models),
        generation_cost=generation,
        judge_calls=calls_total * judge_metrics,
        judge_cost=judge_cost,
        total_cost=total,
        price_known=total is not None,
        models=models,
    )


def estimate_judging(
    judge: ModelProfileOut | None, answers: list[tuple[int, int]], judge_metrics: int, judge_checks: int | None = None
) -> tuple[int, Decimal | None]:
    """Judge calls and cost to score answers that already exist: one call per answer per judged check, each
    reading the stored input and output tokens of the answer plus the judge's own instructions."""
    calls = len(answers) * judge_metrics
    if calls == 0:
        return 0, Decimal(0)
    if judge is None:
        return calls, None
    units = judge_metrics if judge_checks is None else judge_checks
    tokens_in = sum((i + o) * judge_metrics + JUDGE_OVERHEAD_TOKENS * units for i, o in answers)
    tokens_out = JUDGE_REPLY_TOKENS * calls
    return calls, compute_cost(tokens_in, tokens_out, judge.input_price_per_mtok, judge.output_price_per_mtok)
