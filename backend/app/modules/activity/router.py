"""Activity HTTP route (read-only): the workspace's model usage per day, this period and the one before."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.core.security import CurrentPrincipal
from app.modules.activity.dependencies import ActivityDep
from app.modules.activity.schemas import ActivityOut, ActivityQuery

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("")
async def activity(
    principal: CurrentPrincipal, service: ActivityDep, query: Annotated[ActivityQuery, Query()]
) -> ActivityOut:
    return await service.activity(principal, query)
