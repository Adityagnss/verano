"""
Gateway HTTP routes: a single test call to a model, and the project's call history and
cost summary. The test call goes through exactly the same gateway path as every other
LLM call, which is what makes it a meaningful end-to-end check of a key and a model.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.config import Settings, get_settings
from app.core.pagination import Page, PageDep
from app.core.security import CurrentPrincipal
from app.modules.gateway.dependencies import CallHistoryDep, GatewayDep
from app.modules.gateway.schemas import CallContext, CallPurpose, CostSummary, LLMCallOut, LLMResult, TestCallRequest
from app.modules.gateway.service import breaker_for
from app.modules.projects.dependencies import ProjectScope

router = APIRouter(prefix="/projects/{project_id}/llm-calls", tags=["gateway"])


@router.post("")
async def test_call(body: TestCallRequest, project: ProjectScope, gateway: GatewayDep) -> LLMResult:
    context = CallContext(project_id=project.id, labels={"source": "test_call"})
    return await gateway.complete(
        body.model, body.messages, body.params, body.credential_id, CallPurpose.TEST_RUN, context
    )


@router.get("")
async def list_calls(
    project: ProjectScope,
    history: CallHistoryDep,
    page: PageDep,
    purpose: Annotated[CallPurpose | None, Query()] = None,
) -> Page[LLMCallOut]:
    return await history.calls(project.id, page, purpose)


@router.get("/summary")
async def cost_summary(project: ProjectScope, history: CallHistoryDep) -> CostSummary:
    return await history.cost_summary(project.id)


health_router = APIRouter(prefix="/provider-health", tags=["gateway"])


@health_router.get("")
async def provider_health(
    principal: CurrentPrincipal, settings: Annotated[Settings, Depends(get_settings)]
) -> dict[str, str]:
    """Which providers are being paused because they keep failing: provider name to closed, open or half_open."""
    return {provider: state.value for provider, state in breaker_for(settings).snapshot().items()}
