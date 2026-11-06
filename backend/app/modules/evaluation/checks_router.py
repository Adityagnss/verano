"""
Check-writing helpers for the web app: the catalogue of rule checks (so a person can pick one and see its
settings), the limits a custom code check runs under, and a "try it" route that runs a code check on a sample
answer in the sandbox. None of them writes anything.
"""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.container import ContainerDep
from app.core.features import CODE_CHECKS, is_enabled, require_feature
from app.modules.evaluation.plugins.rules import RULES
from app.modules.evaluation.plugins.rules_extra import RULE_INFO
from app.modules.evaluation.schemas import MAX_CODE_CHARS, NEEDS_CODE
from app.modules.projects.dependencies import ProjectScope
from app.sandbox.contract import SandboxLimits, SandboxRequest
from app.sandbox.factory import build_sandbox

router = APIRouter(prefix="/projects/{project_id}", tags=["evaluators"])
MAX_SAMPLE_CHARS = 20_000


class RuleInfoOut(BaseModel):
    name: str
    title: str
    description: str
    settings: str = Field(description="What can be set, as plain text, for example 'values (list), case_sensitive'.")


class CodeLimitsOut(BaseModel):
    wall_s: float
    cpu_s: int
    memory_mb: int
    output_chars: int


class CodeContractOut(BaseModel):
    enabled: bool
    limits: CodeLimitsOut
    max_code_chars: int


class CodeTryRequest(BaseModel):
    code: str = Field(max_length=MAX_CODE_CHARS)
    output: str = Field(default="", max_length=MAX_SAMPLE_CHARS)
    inputs: dict[str, Any] = {}
    expected: str | None = Field(default=None, max_length=MAX_SAMPLE_CHARS)
    rubric: str | None = Field(default=None, max_length=MAX_SAMPLE_CHARS)


class CodeTryOut(BaseModel):
    ok: bool
    score: float | None
    passed: bool | None
    reason: str
    error: str | None
    timed_out: bool


class EvidenceThresholdsOut(BaseModel):
    clearly_better_min_cases: int = Field(
        description="Judged cases needed before two prompts can be called clearly different."
    )
    proven_min_holdout: int = Field(description="Held-back cases needed before an improvement can be called proven.")


@router.get("/evidence-thresholds")
async def evidence_thresholds(project: ProjectScope, container: ContainerDep) -> EvidenceThresholdsOut:
    """The two settings behind the words "clearly better" and "proven", so the screens can state them."""
    settings = container.settings
    return EvidenceThresholdsOut(
        clearly_better_min_cases=settings.compare_min_cases, proven_min_holdout=settings.dataset_min_holdout
    )


def _limits(settings: Any) -> SandboxLimits:
    return SandboxLimits(
        wall_s=settings.sandbox_wall_s,
        cpu_s=settings.sandbox_cpu_s,
        memory_mb=settings.sandbox_memory_mb,
        output_chars=settings.sandbox_output_chars,
    )


@router.get("/rule-checks")
async def list_rule_checks(project: ProjectScope) -> list[RuleInfoOut]:
    """Every rule check that can be added to a project, with what it does and what it can be set to."""
    return [
        RuleInfoOut(name=name, title=info["title"], description=info["description"], settings=info["config"])
        for name, info in RULE_INFO.items()
        if name in RULES
    ]


@router.get("/code-checks/contract")
async def code_check_contract(project: ProjectScope, container: ContainerDep) -> CodeContractOut:
    """The limits a custom code check runs under, and whether this server allows custom code checks."""
    settings = container.settings
    limits = _limits(settings)
    return CodeContractOut(
        enabled=is_enabled(settings, CODE_CHECKS),
        limits=CodeLimitsOut(**limits.model_dump()),
        max_code_chars=MAX_CODE_CHARS,
    )


@router.post("/code-checks/try", dependencies=[Depends(require_feature(CODE_CHECKS))])
async def try_code_check(body: CodeTryRequest, project: ProjectScope, container: ContainerDep) -> CodeTryOut:
    """Run a code check on one sample answer. Nothing is saved; a failing check is a result, not an error."""
    if not body.code.strip():
        return CodeTryOut(ok=False, score=None, passed=None, reason="", error=NEEDS_CODE, timed_out=False)
    settings = container.settings
    request = SandboxRequest(
        code=body.code,
        case={"inputs": body.inputs, "output": body.output, "expected": body.expected, "rubric": body.rubric},
    )
    result = await build_sandbox(settings.sandbox_url).run(request, _limits(settings))
    return CodeTryOut(
        ok=result.ok,
        score=result.score,
        passed=result.passed,
        reason=result.reason,
        error=result.error,
        timed_out=result.timed_out,
    )
