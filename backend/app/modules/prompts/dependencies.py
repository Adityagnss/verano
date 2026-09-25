"""FastAPI wiring for the Prompt Studio service."""

from typing import Annotated

from fastapi import Depends

from app.core.container import SettingsDep
from app.core.database import SessionDep
from app.modules.prompts.service import PromptService
from app.modules.registry.dependencies import RegistryServiceDep


def get_prompt_service(session: SessionDep, registry: RegistryServiceDep, settings: SettingsDep) -> PromptService:
    return PromptService(session, registry, settings)


PromptServiceDep = Annotated[PromptService, Depends(get_prompt_service)]
