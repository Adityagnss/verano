"""
Prompt Studio HTTP routes: prompts, their immutable versions, rendering a version for one
case, checking a saved version, and inspecting an unsaved draft (for the live editor).
"""

import uuid

from fastapi import APIRouter, status

from app.core.pagination import Page, PageDep
from app.core.security import CurrentPrincipal
from app.modules.projects.dependencies import ProjectScope
from app.modules.prompts.dependencies import PromptServiceDep
from app.modules.prompts.schemas import (
    CheckRequest,
    InspectOut,
    InspectRequest,
    PromptCheck,
    PromptCreate,
    PromptOut,
    PromptVersionCreate,
    PromptVersionOut,
    RenderedPrompt,
    RenderRequest,
)

router = APIRouter(prefix="/projects/{project_id}", tags=["prompts"])


@router.post("/prompts", status_code=status.HTTP_201_CREATED)
async def create_prompt(
    body: PromptCreate, project: ProjectScope, principal: CurrentPrincipal, service: PromptServiceDep
) -> PromptOut:
    return await service.create(project, principal, body)


@router.get("/prompts")
async def list_prompts(project: ProjectScope, service: PromptServiceDep, page: PageDep) -> Page[PromptOut]:
    return await service.list_prompts(project, page)


@router.post("/prompts/inspect")
async def inspect_draft(body: InspectRequest, project: ProjectScope, service: PromptServiceDep) -> InspectOut:
    return await service.inspect(project, body)


@router.get("/prompts/{prompt_id}")
async def get_prompt(prompt_id: uuid.UUID, project: ProjectScope, service: PromptServiceDep) -> PromptOut:
    return await service.get_prompt(project, prompt_id)


@router.post("/prompts/{prompt_id}/versions", status_code=status.HTTP_201_CREATED)
async def save_version(
    prompt_id: uuid.UUID,
    body: PromptVersionCreate,
    project: ProjectScope,
    principal: CurrentPrincipal,
    service: PromptServiceDep,
) -> PromptVersionOut:
    return await service.save_version(project.id, principal, prompt_id, body)


@router.get("/prompts/{prompt_id}/versions")
async def list_versions(
    prompt_id: uuid.UUID, project: ProjectScope, service: PromptServiceDep, page: PageDep
) -> Page[PromptVersionOut]:
    return await service.list_versions(project, prompt_id, page)


@router.get("/prompt-versions/{version_id}")
async def get_version(version_id: uuid.UUID, project: ProjectScope, service: PromptServiceDep) -> PromptVersionOut:
    return await service.get_version(project.id, version_id)


@router.post("/prompt-versions/{version_id}/render")
async def render_version(
    version_id: uuid.UUID, body: RenderRequest, project: ProjectScope, service: PromptServiceDep
) -> RenderedPrompt:
    return await service.render_version(project.id, version_id, body.inputs)


@router.post("/prompt-versions/{version_id}/check")
async def check_version(
    version_id: uuid.UUID, body: CheckRequest, project: ProjectScope, service: PromptServiceDep
) -> PromptCheck:
    return await service.check(project, version_id, body)
