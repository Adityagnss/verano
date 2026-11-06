"""
Judging tools HTTP routes (ADR 0038): criteria written by the judge from the task, and the rubric self-check.
Both make judge calls through the gateway (recorded and costed like any other) and write nothing else.
Switched off with the `judging_tools` feature.
"""

from fastapi import APIRouter, Depends

from app.core.features import JUDGING_TOOLS, require_feature
from app.modules.evaluation.dependencies import RubricServiceDep
from app.modules.evaluation.rubric import CriteriaOut, CriteriaRequest, RubricCheckOut, RubricCheckRequest
from app.modules.projects.dependencies import ProjectScope

router = APIRouter(
    prefix="/projects/{project_id}/judge",
    tags=["judging"],
    dependencies=[Depends(require_feature(JUDGING_TOOLS))],
)


@router.post("/criteria")
async def write_criteria(body: CriteriaRequest, project: ProjectScope, service: RubricServiceDep) -> CriteriaOut:
    """The judge writes criteria from the Task Spec and the prompt, then the self-check reads them."""
    return await service.generate(project.id, body)


@router.post("/rubric-check")
async def check_rubric(body: RubricCheckRequest, project: ProjectScope, service: RubricServiceDep) -> RubricCheckOut:
    """Is every criterion answerable, specific and consistent? Free checks, plus a judge's read when one is given."""
    return await service.check(project.id, body)
