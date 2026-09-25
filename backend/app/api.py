"""
API router assembly: mounts every module router under the versioned prefix (/api/v1).
Adding a module's routes to the API is one line here.
"""

from fastapi import APIRouter

from app.modules.auth.router import router as auth_router
from app.modules.gateway.router import router as gateway_router
from app.modules.projects.router import router as projects_router
from app.modules.registry.router import router as registry_router

api_router = APIRouter()
for module_router in (auth_router, projects_router, registry_router, gateway_router):
    api_router.include_router(module_router)
