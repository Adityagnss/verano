"""
Improve HTTP routes: start an improvement session from a scored experiment, the latest
session for an experiment, one session (clusters, candidates, holdout verdict), and
accepting the winning candidate as the prompt's new version.
"""

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Query, status
from pydantic import BaseModel

from app.core.security import CurrentPrincipal
from app.modules.assistant.dependencies import ImprovementServiceDep
from app.modules.assistant.schemas import ImprovementOut, ImproveRequest
from app.modules.projects.dependencies import ProjectScope

router = APIRouter(prefix="/projects/{project_id}/improvements", tags=["improve"])
notes_router = APIRouter(prefix="/prompt-notes", tags=["improve"])
GUIDE = Path(__file__).parent / "prompts" / "prompt_guide.md"


class PromptNotes(BaseModel):
    markdown: str


@notes_router.get("")
async def prompt_notes(principal: CurrentPrincipal) -> PromptNotes:
    """The Prompt guide page: the full prompting reference (a superset of the notes Improve reads)."""
    return PromptNotes(markdown=GUIDE.read_text(encoding="utf-8"))


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def start_improvement(
    body: ImproveRequest, project: ProjectScope, service: ImprovementServiceDep
) -> ImprovementOut:
    return await service.start(project, body.experiment_id, body.writer)


@router.get("/latest")
async def latest_improvement(
    project: ProjectScope, service: ImprovementServiceDep, experiment_id: Annotated[uuid.UUID, Query()]
) -> ImprovementOut | None:
    return await service.latest(project, experiment_id)


@router.get("/{session_id}")
async def get_improvement(
    session_id: uuid.UUID, project: ProjectScope, service: ImprovementServiceDep
) -> ImprovementOut:
    return await service.get(project.id, session_id)


@router.post("/{session_id}/candidates/{candidate_id}/accept")
async def accept_candidate(
    session_id: uuid.UUID,
    candidate_id: uuid.UUID,
    project: ProjectScope,
    principal: CurrentPrincipal,
    service: ImprovementServiceDep,
) -> ImprovementOut:
    return await service.accept(project, principal, session_id, candidate_id)
