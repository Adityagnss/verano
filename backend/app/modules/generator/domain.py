"""
Pure Eval Generator logic (DEVELOPMENT.md 2.3). No I/O.

- `suggest_generator` picks the default generator model: the selected model with the
  lowest known output price (a smaller model is enough to write test cases, decision 48);
  if none is priced (only local models), the largest local model by the parameter size in
  its name.
- `plan_targets` decides how many cases each category still needs: the dataset is
  `target size` (or the real row count if larger), split by the category shares; real
  rows count toward their own category (happy_path if theirs isn't one), and generation
  only fills what is missing.
- `near_duplicates` returns the new cases whose similarity to any kept case (real rows
  first, so they are never dropped) is above the threshold.
- `missing_labels` lists allowed classification labels no case covers yet.
- `answer_label` matches a drafted classification answer to its allowed label, or None.
- `select_evaluators` turns the Task Spec into the evaluator set (Step E).
- `estimate_calls` sizes a run for the cost preview shown before generating.
"""

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from app.core.text import clip
from app.modules.generator.schemas import CaseCategory, OutputFormat, TaskSpec, TaskType
from app.modules.registry.schemas import ModelProfileOut

SIZE_IN_NAME = re.compile(r"(\d+(?:\.\d+)?)\s*b\b", re.IGNORECASE)
SINGLE_ANSWER_TYPES = {TaskType.CLASSIFICATION, TaskType.EXTRACTION}


class CategorySpec(BaseModel):
    share: float
    instruction: str


class GenerationCatalog(BaseModel):
    categories: dict[CaseCategory, CategorySpec]


class EvaluatorTemplate(BaseModel):
    name: str
    version: str
    kind: str
    threshold: float | None = None
    weight: float | None = None
    required: bool | None = None
    config: dict[str, Any] = {}
    from_spec: list[str] = []


class EvaluatorCatalog(BaseModel):
    defaults: dict[str, Any]
    constraints: EvaluatorTemplate
    task_types: dict[TaskType, list[EvaluatorTemplate]]


@dataclass(frozen=True)
class EvaluatorChoice:
    name: str
    version: str
    config: dict[str, Any]
    threshold: float
    weight: float
    required: bool


def _local_size(profile: ModelProfileOut) -> float:
    match = SIZE_IN_NAME.search(profile.model_name)
    return float(match.group(1)) if match else 0.0


def suggest_generator(profiles: Sequence[ModelProfileOut]) -> ModelProfileOut | None:
    priced = [p for p in profiles if p.output_price_per_mtok is not None and p.output_price_per_mtok > Decimal(0)]
    if priced:
        return min(priced, key=lambda p: p.output_price_per_mtok or Decimal(0))
    return max(profiles, key=_local_size, default=None)


def is_single_answer(spec: TaskSpec) -> bool:
    return spec.task_type in SINGLE_ANSWER_TYPES or spec.output_format in {
        OutputFormat.SINGLE_LABEL,
        OutputFormat.JSON,
    }


def plan_targets(
    catalog: GenerationCatalog, target_size: int, real: dict[str, int], existing: dict[str, int]
) -> dict[CaseCategory, int]:
    """
    Cases still to generate per category. `real` counts real rows by category (a category
    outside the catalog counts as happy_path); `existing` counts generated cases already
    kept. A category the real rows already fill gets nothing more.
    """
    size = max(target_size, sum(real.values()))
    wanted = {category: math.floor(spec.share * size) for category, spec in catalog.categories.items()}
    wanted[CaseCategory.HAPPY_PATH] += size - sum(wanted.values())
    covered: dict[str, int] = {}
    for category, count in real.items():
        key = category if category in wanted else CaseCategory.HAPPY_PATH
        covered[key] = covered.get(key, 0) + count
    return {
        category: max(0, count - covered.get(category, 0) - existing.get(category, 0))
        for category, count in wanted.items()
    }


def near_duplicates(kept: list[list[float]], new: list[list[float]], threshold: float) -> list[int]:
    """Indexes of `new` that duplicate a kept vector or an earlier new one."""
    pool = list(kept)
    dropped = []
    for index, vector in enumerate(new):
        if any(sum(a * b for a, b in zip(vector, other, strict=True)) > threshold for other in pool):
            dropped.append(index)
        else:
            pool.append(vector)
    return dropped


def normalize_label(value: str) -> str:
    return " ".join(value.strip().strip(".\"'").lower().split())


def answer_label(answer: str | None, allowed: list[str]) -> str | None:
    if answer is None:
        return None
    by_normal = {normalize_label(label): label for label in allowed}
    return by_normal.get(normalize_label(answer))


def missing_labels(spec: TaskSpec, answers: Sequence[str | None]) -> list[str]:
    if spec.task_type is not TaskType.CLASSIFICATION or not spec.allowed_outputs:
        return []
    covered = {answer_label(answer, spec.allowed_outputs) for answer in answers}
    return [label for label in spec.allowed_outputs if label not in covered]


def case_text(inputs: dict[str, Any]) -> str:
    return "\n".join(str(value) for _, value in sorted(clip(inputs).items()))


def select_evaluators(spec: TaskSpec, catalog: EvaluatorCatalog) -> list[EvaluatorChoice]:
    templates = list(catalog.task_types[spec.task_type])
    if spec.constraints:
        templates.append(catalog.constraints)
    choices = []
    for template in templates:
        config = dict(template.config)
        for field in template.from_spec:
            config[field] = getattr(spec, field)
        choices.append(
            EvaluatorChoice(
                name=template.name,
                version=template.version,
                config={"kind": template.kind, **config},
                threshold=template.threshold if template.threshold is not None else catalog.defaults["threshold"],
                weight=template.weight if template.weight is not None else catalog.defaults["weight"],
                required=template.required if template.required is not None else catalog.defaults["required"],
            )
        )
    return choices


# Rough token sizes behind the cost preview; a preview, not a bill (the gateway records the real cost).
CALL_OVERHEAD_TOKENS = 1_200
TOKENS_PER_CASE_OUT = 60
TOKENS_PER_ANSWER_IN = 80
TOKENS_PER_ANSWER_OUT = 40


@dataclass(frozen=True)
class Estimate:
    calls: int
    input_tokens: int
    output_tokens: int


def estimate_calls(targets: dict[CaseCategory, int], answers: int, batch: int, answer_batch: int) -> Estimate:
    case_calls = sum(math.ceil(count / batch) for count in targets.values())
    answer_calls = math.ceil(answers / answer_batch)
    cases = sum(targets.values())
    return Estimate(
        calls=case_calls + answer_calls,
        input_tokens=(case_calls + answer_calls) * CALL_OVERHEAD_TOKENS + answers * TOKENS_PER_ANSWER_IN,
        output_tokens=cases * TOKENS_PER_CASE_OUT + answers * TOKENS_PER_ANSWER_OUT,
    )
