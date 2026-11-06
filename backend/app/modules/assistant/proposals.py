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
from app.modules.assistant.failures import MAX_FAILURES as MAX_FAILURES
from app.modules.assistant.failures import FailureAnalysis
from app.modules.assistant.models import OptimizationSession, PromptCandidate
from app.modules.assistant.repository import AssistantRepository
from app.modules.assistant.schemas import CandidateDrafts, CandidateOutcome, ClusterNames, FailureGroups
from app.modules.engine.models import Experiment
from app.modules.evaluation.domain import inputs_text
from app.modules.evaluation.schemas import CaseResultOut
from app.modules.prompts.domain import TemplateInfo, analyze
from app.modules.prompts.schemas import PromptSource, PromptVersionCreate, PromptVersionOut
from app.modules.prompts.service import PromptService

CANDIDATES = 3
NAMED_CLUSTERS = 12
SAME_PROMPT = "The suggestion is the current prompt again, so there is nothing to test."
CHANGES_INPUTS = (
    "The suggestion changes the inputs the prompt takes (or its shape), so it could not be tested on these cases."
)


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


async def store_cluster_analysis(
    repo: AssistantRepository,
    baseline: Experiment,
    run_id: uuid.UUID,
    analysis: FailureAnalysis,
    names: ClusterNames | None,
) -> list[FailureCluster]:
    """One failure cluster per automatic group; the biggest ones are named by the model, the rest are pooled into
    one "Other failures" group so the page stays readable."""
    await repo.replace_clusters(run_id)
    named = {g.cluster: g for g in (names.groups if names else [])}
    shown = analysis.clusters[:NAMED_CLUSTERS]
    pooled = analysis.clusters[NAMED_CLUSTERS:]
    clusters = []
    for index, group in enumerate(shown):
        found = named.get(index)
        tag = group.tags.most_common(1)[0][0] if group.tags else "low_quality"
        clusters.append(
            _cluster(
                baseline,
                run_id,
                found.name if found else f"Failure group {index + 1}",
                found.hypothesis if found else f"Most of these failed as {tag}.",
                tag,
                group.size,
                group.models,
                group.categories,
                group.examples,
            )
        )
    if pooled:
        tags: Counter[str] = Counter()
        models: Counter[str] = Counter()
        categories: Counter[str] = Counter()
        for group in pooled:
            tags.update(group.tags)
            models.update(group.models)
            categories.update(group.categories)
        clusters.append(
            _cluster(
                baseline,
                run_id,
                "Other failures",
                "Smaller groups that did not fit the larger ones.",
                tags.most_common(1)[0][0] if tags else "low_quality",
                sum(g.size for g in pooled),
                models,
                categories,
                [e for g in pooled for e in g.examples][:5],
            )
        )
    for cluster in clusters:
        await repo.add(cluster)
    return clusters


def _cluster(
    baseline: Experiment,
    run_id: uuid.UUID,
    name: str,
    hypothesis: str,
    tag: str,
    size: int,
    models: Counter[str],
    categories: Counter[str],
    examples: list[dict[str, Any]],
) -> FailureCluster:
    return FailureCluster(
        experiment_id=baseline.id,
        evaluation_run_id=run_id,
        name=name[:200],
        hypothesis=hypothesis,
        rule_tag=tag,
        size=size,
        affected_models=sorted(models),
        categories=sorted(categories),
        example_case_ids=[e["run_id"] for e in examples[:5]],
    )


async def store_candidates(
    repo: AssistantRepository,
    prompts: PromptService,
    row: OptimizationSession,
    baseline: Experiment,
    prompt: PromptVersionOut,
    drafts: CandidateDrafts,
    clusters: list[FailureCluster],
    round_number: int = 1,
    parent_candidate_id: uuid.UUID | None = None,
    limit: int = CANDIDATES,
) -> list[PromptCandidate]:
    """Every draft the model wrote is kept in the backend. One that can be tested becomes a candidate version; one
    that cannot (it changes the prompt's inputs, or it is the current prompt again) is stored as rejected with the
    reason and its text, so the session history shows what was tried."""
    by_name = {c.name: str(c.id) for c in clusters}
    created = []
    current = analyze(prompt.system_template, prompt.user_template)
    for draft in drafts.candidates[:limit]:
        system, user = draft.system_template or None, draft.user_template or None
        common: dict[str, Any] = {
            "session_id": row.id,
            "base_prompt_version_id": prompt.id,
            "strategy": draft.strategy[:64],
            "target_cluster_ids": [by_name[name] for name in draft.target_groups if name in by_name],
            "diff": prompt_diff((prompt.system_template, prompt.user_template), (system, user)),
            "change_reasons": draft.change_reasons,
            "round": round_number,
            "parent_candidate_id": parent_candidate_id,
        }
        problem = None
        if (system, user) == (prompt.system_template, prompt.user_template):
            problem = SAME_PROMPT
        elif not keeps_inputs(current, system, user):
            problem = CHANGES_INPUTS
        if problem is not None:
            await repo.add(
                PromptCandidate(
                    **common,
                    prompt_version_id=None,
                    outcome=CandidateOutcome.REJECTED,
                    rejection_reason=problem,
                    rejected_draft={"system_template": system, "user_template": user},
                )
            )
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
        candidate = PromptCandidate(**common, prompt_version_id=version.id, outcome=CandidateOutcome.PENDING)
        await repo.add(candidate)
        created.append(candidate)
    return created
