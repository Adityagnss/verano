"""
API router assembly: mounts every module router under the versioned prefix (/api/v1).
Adding a module's routes to the API is one line here.
"""

from fastapi import APIRouter, Depends

from app.modules.activity.router import router as activity_router
from app.modules.apps.router import router as apps_router
from app.modules.assistant.router import notes_router
from app.modules.assistant.router import router as improve_router
from app.modules.audit.router import router as audit_router
from app.modules.auth.members_router import router as members_router
from app.modules.auth.router import router as auth_router
from app.modules.datasets.review_router import router as review_router
from app.modules.datasets.router import router as datasets_router
from app.modules.documents.router import router as documents_router
from app.modules.engine.router import router as engine_router
from app.modules.evaluation.router import project_router as evaluators_router
from app.modules.evaluation.router import router as results_router
from app.modules.gateway.router import router as gateway_router
from app.modules.generator.router import router as generator_router
from app.modules.logbook.router import router as logbook_router
from app.modules.organizations.router import router as organizations_router
from app.modules.projects.access import enforce_permissions
from app.modules.projects.router import router as projects_router
from app.modules.prompts.router import router as prompts_router
from app.modules.registry.router import router as registry_router

api_router = APIRouter()
for module_router in (
    auth_router,
    members_router,
    organizations_router,
    audit_router,
    projects_router,
    registry_router,
    apps_router,
    gateway_router,
    activity_router,
    prompts_router,
    datasets_router,
    documents_router,
    generator_router,
    review_router,
    engine_router,
    results_router,
    evaluators_router,
    improve_router,
    notes_router,
    logbook_router,
):
    # every route passes the one permission check (app/core/permissions.py) before its handler runs
    api_router.include_router(module_router, dependencies=[Depends(enforce_permissions)])
