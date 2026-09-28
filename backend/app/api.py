"""
API router assembly: mounts every module router under the versioned prefix (/api/v1).
Adding a module's routes to the API is one line here.
"""

from fastapi import APIRouter

from app.modules.auth.router import router as auth_router
from app.modules.datasets.router import router as datasets_router
from app.modules.documents.router import router as documents_router
from app.modules.gateway.router import router as gateway_router
from app.modules.projects.router import router as projects_router
from app.modules.prompts.router import router as prompts_router
from app.modules.registry.router import router as registry_router

api_router = APIRouter()
for module_router in (
    auth_router,
    projects_router,
    registry_router,
    gateway_router,
    prompts_router,
    datasets_router,
    documents_router,
):
    api_router.include_router(module_router)
