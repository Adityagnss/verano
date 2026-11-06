"""
Security HTTP routes: the attack families, packs (generate, review cases, approve), running a pack, the report and
gate for a run, and "harden". Every route needs the project and can be switched off (feature `security`).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.container import ContainerDep
from app.core.database import SessionDep
from app.core.features import SECURITY, require_feature
from app.core.security import CurrentPrincipal
from app.modules.assistant.schemas import ImprovementOut
from app.modules.engine.schemas import ExperimentOut
from app.modules.projects.dependencies import ProjectScope
from app.modules.security.schemas import (
    AttackFamilyOut,
    BulkReview,
    CaseOut,
    CaseUpdate,
    GateOut,
    HardenRequest,
    PackCreate,
    PackDetail,
    PackOut,
    SecurityReport,
    SecurityRunRequest,
)
from app.modules.security.service import SecurityService


def get_security_service(session: SessionDep, container: ContainerDep) -> SecurityService:
    return SecurityService(session, container)


SecurityServiceDep = Annotated[SecurityService, Depends(get_security_service)]
router = APIRouter(
    prefix="/projects/{project_id}/security",
    tags=["security"],
    dependencies=[Depends(require_feature(SECURITY))],
)


@router.get("/families")
async def attack_families(project: ProjectScope, service: SecurityServiceDep) -> list[AttackFamilyOut]:
    """The kinds of attack the pack can contain, with the OWASP LLM Top 10 entry each belongs to."""
    return service.families()


@router.post("/packs", status_code=status.HTTP_202_ACCEPTED)
async def create_pack(
    body: PackCreate, project: ProjectScope, principal: CurrentPrincipal, service: SecurityServiceDep
) -> PackOut:
    return await service.create_pack(project, principal, body)


@router.get("/packs")
async def list_packs(project: ProjectScope, service: SecurityServiceDep) -> list[PackOut]:
    return await service.list_packs(project)


@router.get("/packs/{pack_id}")
async def get_pack(pack_id: uuid.UUID, project: ProjectScope, service: SecurityServiceDep) -> PackDetail:
    return await service.get_pack(project, pack_id)


@router.delete("/packs/{pack_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pack(pack_id: uuid.UUID, project: ProjectScope, service: SecurityServiceDep) -> None:
    await service.delete_pack(project, pack_id)


@router.patch("/packs/{pack_id}/cases/{case_id}")
async def update_case(
    pack_id: uuid.UUID, case_id: uuid.UUID, body: CaseUpdate, project: ProjectScope, service: SecurityServiceDep
) -> CaseOut:
    """Edit an attack, its expected safe behaviour, or approve or reject it. Editing counts as approving."""
    return await service.update_case(project, pack_id, case_id, body)


@router.post("/packs/{pack_id}/review")
async def review_all(
    pack_id: uuid.UUID, body: BulkReview, project: ProjectScope, service: SecurityServiceDep
) -> PackOut:
    """Approve (or reject) every case that is still a draft, optionally only one category."""
    return await service.review_all(project, pack_id, body)


@router.post("/packs/{pack_id}/approve")
async def approve_pack(
    pack_id: uuid.UUID, project: ProjectScope, principal: CurrentPrincipal, service: SecurityServiceDep
) -> PackOut:
    """Freeze the approved cases into the security test set, ready to run."""
    return await service.approve(project, principal, pack_id)


@router.post("/packs/{pack_id}/runs", status_code=status.HTTP_201_CREATED)
async def run_pack(
    pack_id: uuid.UUID,
    body: SecurityRunRequest,
    project: ProjectScope,
    principal: CurrentPrincipal,
    service: SecurityServiceDep,
) -> ExperimentOut:
    return await service.run(project, principal, pack_id, body)


@router.get("/packs/{pack_id}/report")
async def report(
    pack_id: uuid.UUID,
    project: ProjectScope,
    service: SecurityServiceDep,
    experiment_id: Annotated[uuid.UUID, Query()],
) -> SecurityReport:
    return await service.report(project, pack_id, experiment_id)


@router.get("/packs/{pack_id}/gate")
async def gate(
    pack_id: uuid.UUID,
    project: ProjectScope,
    service: SecurityServiceDep,
    experiment_id: Annotated[uuid.UUID, Query()],
    min_pass_rate: Annotated[float, Query(ge=0, le=1)] = 0.8,
    max_drop: Annotated[float | None, Query(ge=0, le=1)] = 0.05,
) -> GateOut:
    """What `verano run --ci --security` reads: categories below the minimum, or down since the last run."""
    return await service.gate(project, pack_id, experiment_id, min_pass_rate, max_drop)


@router.post("/packs/{pack_id}/harden", status_code=status.HTTP_202_ACCEPTED)
async def harden(
    pack_id: uuid.UUID, body: HardenRequest, project: ProjectScope, service: SecurityServiceDep
) -> ImprovementOut:
    """Improve proposes added instructions and re-tests them on held-back attack cases."""
    return await service.harden(project, pack_id, body)
