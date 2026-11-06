"""
Prompt label HTTP routes: set, move, remove and roll back a label, read its history, choose
whether Accept moves a label, and the route an app calls to get the prompt a label points at.

The fetch route answers with an ETag; a caller that sends it back in `If-None-Match` gets an
empty 304 when nothing changed. It is a plain GET, so a read-only API token can use it.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response, status

from app.core.features import PROMPT_LABELS, require_feature
from app.core.pagination import Page, PageDep
from app.core.security import CurrentPrincipal
from app.modules.projects.dependencies import ProjectScope
from app.modules.prompts.dependencies import PromptServiceDep
from app.modules.prompts.label_schemas import (
    FetchedPrompt,
    LabelAssign,
    LabelMoveOut,
    LabelName,
    LabelSettingsUpdate,
    LabelsOut,
    PromptLabelOut,
)

router = APIRouter(
    prefix="/projects/{project_id}", tags=["prompt labels"], dependencies=[Depends(require_feature(PROMPT_LABELS))]
)


@router.get("/prompts/{prompt_id}/labels")
async def list_labels(prompt_id: uuid.UUID, project: ProjectScope, service: PromptServiceDep) -> LabelsOut:
    return await service.labels.list(project.id, prompt_id)


@router.put("/prompts/{prompt_id}/labels/{name}")
async def set_label(
    prompt_id: uuid.UUID,
    name: LabelName,
    body: LabelAssign,
    project: ProjectScope,
    principal: CurrentPrincipal,
    service: PromptServiceDep,
) -> PromptLabelOut:
    return await service.labels.assign(project.id, principal, prompt_id, name, body.version_id)


@router.delete("/prompts/{prompt_id}/labels/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_label(
    prompt_id: uuid.UUID, name: LabelName, project: ProjectScope, principal: CurrentPrincipal, service: PromptServiceDep
) -> None:
    await service.labels.remove(project.id, principal, prompt_id, name)


@router.post("/prompts/{prompt_id}/labels/{name}/rollback")
async def roll_back_label(
    prompt_id: uuid.UUID, name: LabelName, project: ProjectScope, principal: CurrentPrincipal, service: PromptServiceDep
) -> PromptLabelOut:
    return await service.labels.rollback(project.id, principal, prompt_id, name)


@router.get("/prompts/{prompt_id}/label-history")
async def label_history(
    prompt_id: uuid.UUID,
    project: ProjectScope,
    service: PromptServiceDep,
    page: PageDep,
    label: Annotated[LabelName | None, Query()] = None,
) -> Page[LabelMoveOut]:
    return await service.labels.history(project.id, prompt_id, label, page)


@router.put("/prompts/{prompt_id}/label-settings")
async def set_label_settings(
    prompt_id: uuid.UUID, body: LabelSettingsUpdate, project: ProjectScope, service: PromptServiceDep
) -> LabelsOut:
    return await service.labels.set_accept_label(project.id, prompt_id, body.accept_moves_label)


@router.get(
    "/prompt-by-name/{name}",
    response_model=FetchedPrompt,
    responses={status.HTTP_304_NOT_MODIFIED: {"description": "The prompt has not changed since the ETag you sent."}},
)
async def fetch_prompt(
    name: str,
    response: Response,
    project: ProjectScope,
    service: PromptServiceDep,
    label: Annotated[LabelName | None, Query()] = None,
    version: Annotated[int | None, Query(ge=1)] = None,
    if_none_match: Annotated[str | None, Header()] = None,
) -> FetchedPrompt | Response:
    """The prompt an app should use: the version a label points at (for example `production`), a given version
    number, or the latest saved version when neither is asked for."""
    fetched, etag = await service.labels.fetch(project.id, name, label, version)
    headers = {"ETag": etag, "Cache-Control": "private, no-cache"}
    if if_none_match is not None and etag in {tag.strip() for tag in if_none_match.split(",")}:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    response.headers.update(headers)
    return fetched
