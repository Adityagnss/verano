"""
Stability: do repeated runs give the same answer (DEVELOPMENT.md H2 step 3)?

This is about the answers themselves, not their scores: the pass/fail *consistency* in
`metrics.py` can be steady while the wording changes, and the other way round. Two answers
are the same when their text matches after whitespace is collapsed, or, for JSON answers,
when the parsed values match (key order and spacing don't matter). Nothing fuzzy.

Per test case and model with 2+ answered runs: the largest group of matching answers out of
the runs ("same answer in 4 of 5 runs"). Failed calls have no answer and are left out; a case
with fewer than 2 answers can't be compared. The same comparison, call by call, tells whether
a re-run of the same configuration reproduced the first one.
"""

import json
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from statistics import mean


@dataclass(frozen=True)
class Answer:
    model_profile_id: uuid.UUID
    dataset_item_id: uuid.UUID
    run_number: int
    output: str


@dataclass(frozen=True)
class Agreement:
    same: int
    runs: int


@dataclass(frozen=True)
class ModelStability:
    stability: float | None
    stable_cases: int
    compared_cases: int


@dataclass(frozen=True)
class Replication:
    same: int
    compared: int
    skipped: int


def normalize(text: str) -> str:
    stripped = text.strip()
    try:
        return json.dumps(json.loads(stripped), sort_keys=True, ensure_ascii=False)
    except ValueError:
        return " ".join(stripped.split())


def agreement(outputs: list[str]) -> Agreement:
    groups = Counter(normalize(output) for output in outputs)
    return Agreement(same=max(groups.values()), runs=len(outputs))


def case_agreements(answers: list[Answer]) -> dict[tuple[uuid.UUID, uuid.UUID], Agreement]:
    """(model, test case) -> agreement, only where there are 2+ answers to compare."""
    grouped: dict[tuple[uuid.UUID, uuid.UUID], list[str]] = defaultdict(list)
    for answer in answers:
        grouped[(answer.model_profile_id, answer.dataset_item_id)].append(answer.output)
    return {key: agreement(outputs) for key, outputs in grouped.items() if len(outputs) > 1}


def model_stability(answers: list[Answer]) -> dict[uuid.UUID, ModelStability]:
    per_model: dict[uuid.UUID, list[Agreement]] = defaultdict(list)
    for (model_id, _), case in case_agreements(answers).items():
        per_model[model_id].append(case)
    result = {}
    for model_id in {a.model_profile_id for a in answers}:
        cases = per_model.get(model_id, [])
        result[model_id] = ModelStability(
            stability=mean(a.same / a.runs for a in cases) if cases else None,
            stable_cases=sum(a.same == a.runs for a in cases),
            compared_cases=len(cases),
        )
    return result


def replication(current: list[Answer], earlier: list[Answer]) -> dict[uuid.UUID, Replication]:
    """Per model: calls (same case, same run number) that gave the same answer in both experiments.
    `skipped` counts answers of this experiment with no answer to compare against in the other."""
    before = {(a.dataset_item_id, a.model_profile_id, a.run_number): normalize(a.output) for a in earlier}
    counts: dict[uuid.UUID, list[int]] = defaultdict(lambda: [0, 0, 0])
    for answer in current:
        tally = counts[answer.model_profile_id]
        old = before.get((answer.dataset_item_id, answer.model_profile_id, answer.run_number))
        if old is None:
            tally[2] += 1
            continue
        tally[1] += 1
        tally[0] += old == normalize(answer.output)
    return {model_id: Replication(*tally) for model_id, tally in counts.items()}
