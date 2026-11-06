"""
The proposal half of Improve: failed outputs with their rule tags, failure clusters from
the model's named groups, and candidate prompt versions (kept only when they need exactly
the inputs the current prompt needs), each with its diff and change reasons.
"""

import uuid
from collections import Counter
from typing import Any

from app.core.text import clip
from app.modules.analysis.models import FailureCluster
from app.modules.assistant.domain import prompt_diff, rule_tag
from app.modules.assistant.models import OptimizationSession, PromptCandidate
from app.modules.assistant.repository import AssistantRepository
from app.modules.assistant.schemas import CandidateDrafts, CandidateOutcome, FailureGroups
from app.modules.engine.models import Experiment
from app.modules.evaluation.domain import inputs_text
from app.modules.evaluation.schemas import CaseResultOut
from app.modules.prompts.domain import TemplateInfo, analyze
from app.modules.prompts.schemas import PromptSource, PromptVersionCreate, PromptVersionOut
from app.modules.prompts.service import PromptService

MAX_FAILURES = 40
CANDIDATES = 3


def failures_of(cases: list[CaseResultOut]) -> list[dict[str, Any]]:
    """Every failed output of these cases, with its rule tag, capped at MAX_FAILURES."""
    failures = []
    for case in cases:
        for output in case.outputs:
            if output.passed:
                continue
            failed = {s.evaluator_name for s in output.scores if not s.passed}
            failures.append(
                {
                    "run_id": str(output.test_case_run_id),
                    "tag": rule_tag(output.output, failed),
                    "model": output.model,
                    "category": case.category,
                    "inputs": clip(case.inputs)
                    if set(case.inputs) != {"attachment"}
                    else inputs_text(clip(case.inputs)),
                    "expected": case.expected_output,
                    "output": output.output or output.error,
                    "reasons": "; ".join(s.reason for s in output.scores if not s.passed),
                }
            )
    return failures[:MAX_FAILURES]


async def store_clusters(
    repo: AssistantRepository,
    baseline: Experiment,
    run_id: uuid.UUID,
    groups: FailureGroups,
    failures: list[dict[str, Any]],
) -> list[FailureCluster]:
    await repo.replace_clusters(run_id)
    clusters = []
    for group in groups.groups:
        members = [failures[i] for i in group.cases if 0 <= i < len(failures)] or failures[:1]
        cluster = FailureCluster(
            experiment_id=baseline.id,
            evaluation_run_id=run_id,
            name=group.name,
            hypothesis=group.hypothesis,
            rule_tag=Counter(m["tag"] for m in members).most_common(1)[0][0],
            size=len(members),
            affected_models=sorted({m["model"] for m in members}),
            categories=sorted({m["category"] for m in members}),
            example_case_ids=[m["run_id"] for m in members[:5]],
        )
        await repo.add(cluster)
        clusters.append(cluster)
    return clusters


def keeps_inputs(current: TemplateInfo, system: str | None, user: str | None) -> bool:
    """A candidate can be tested only if it takes the same inputs in the same shape: a prompt that gains or loses its
    user message stops mapping the cases' inputs (a real case's `attachment` fills a system-only prompt only)."""
    if system is None and user is None:
        return False
    info = analyze(system, user)
    return info.required_inputs == current.required_inputs and info.shape == current.shape


async def store_candidates(
    repo: AssistantRepository,
    prompts: PromptService,
    row: OptimizationSession,
    baseline: Experiment,
    prompt: PromptVersionOut,
    drafts: CandidateDrafts,
    clusters: list[FailureCluster],
) -> list[PromptCandidate]:
    by_name = {c.name: str(c.id) for c in clusters}
    created = []
    for draft in drafts.candidates[:CANDIDATES]:
        system, user = draft.system_template or None, draft.user_template or None
        if not keeps_inputs(analyze(prompt.system_template, prompt.user_template), system, user):
            continue
        body = PromptVersionCreate(
            system_template=system,
            user_template=user,
            default_params=prompt.default_params,
            change_reason=f"Candidate: {draft.strategy}",
            parent_version_id=prompt.id,
        )
        version = await prompts.save_version(
            baseline.project_id, None, prompt.prompt_id, body, source=PromptSource.ASSISTANT, candidate=True
        )
        candidate = PromptCandidate(
            session_id=row.id,
            base_prompt_version_id=prompt.id,
            prompt_version_id=version.id,
            strategy=draft.strategy[:64],
            target_cluster_ids=[by_name[name] for name in draft.target_groups if name in by_name],
            diff=prompt_diff((prompt.system_template, prompt.user_template), (system, user)),
            change_reasons=draft.change_reasons,
            outcome=CandidateOutcome.PENDING,
        )
        await repo.add(candidate)
        created.append(candidate)
    return created
