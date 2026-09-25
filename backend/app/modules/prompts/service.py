"""
Prompt Studio use cases: prompts and immutable versions, rendering, and pre-run checks.

Every save is a new version (1, 2, 3, ...) linked to its parent, with its source (manual or
assistant) and change reason; nothing is ever updated in place. Templates are parsed on
save, so a syntax error is reported before anything runs, and default parameters must be
ones the provider catalog knows. `check` and `inspect` answer "will this prompt work?":
every required input can be filled from the data's columns, and the rendered prompt plus
the reply budget fits each selected model's context window. `inspect` does the same for an
unsaved draft, for the live Prompt screen. Other modules render cases through
`render_version`.
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import NotFound, ValidationFailed
from app.core.pagination import Page, PageParams, to_page
from app.core.security import Principal
from app.modules.projects.schemas import ProjectOut
from app.modules.prompts.domain import TemplateInfo, analyze, context_fits, missing_inputs, render
from app.modules.prompts.models import Prompt, PromptVersion
from app.modules.prompts.repository import PromptRepository
from app.modules.prompts.schemas import (
    CheckRequest,
    InspectOut,
    InspectRequest,
    PromptCheck,
    PromptCreate,
    PromptOut,
    PromptSource,
    PromptTemplates,
    PromptVersionCreate,
    PromptVersionOut,
    RenderedPrompt,
)
from app.modules.registry.service import RegistryService

PROMPT_NOT_FOUND = "This prompt doesn't exist in this project."
VERSION_NOT_FOUND = "This prompt version doesn't exist in this project."
PARENT_ELSEWHERE = "The parent version belongs to a different prompt."
TOO_LONG = "The {label} prompt is {length:,} characters long; the limit is {limit:,}."
UNKNOWN_PARAMS = "Unknown parameters: {names}. Use only: {known}."


def version_out(row: PromptVersion) -> PromptVersionOut:
    info = analyze(row.system_template, row.user_template)
    return PromptVersionOut.model_validate(
        {
            **{name: getattr(row, name) for name in PromptVersionOut.model_fields if hasattr(row, name)},
            "shape": info.shape,
            "required_inputs": info.required_inputs,
        }
    )


class PromptService:
    def __init__(self, session: AsyncSession, registry: RegistryService, settings: Settings) -> None:
        self._repo = PromptRepository(session)
        self._registry = registry
        self._settings = settings

    async def create(self, project: ProjectOut, principal: Principal, body: PromptCreate) -> PromptOut:
        prompt = Prompt(project_id=project.id, name=body.name)
        await self._repo.add(prompt)
        version = await self._save(prompt, principal, body, parent_version_id=None, number=1)
        return PromptOut(
            id=prompt.id, project_id=project.id, name=prompt.name, created_at=prompt.created_at, latest_version=version
        )

    async def save_version(
        self,
        project: ProjectOut,
        principal: Principal | None,
        prompt_id: uuid.UUID,
        body: PromptVersionCreate,
        source: PromptSource = PromptSource.MANUAL,
    ) -> PromptVersionOut:
        prompt = await self._prompt(project.id, prompt_id, lock=True)
        parent = body.parent_version_id or (await self._repo.latest_versions([prompt.id]))[prompt.id].id
        if (await self._version(project.id, parent)).prompt_id != prompt.id:
            raise ValidationFailed(PARENT_ELSEWHERE)
        number = await self._repo.next_version_number(prompt.id)
        return await self._save(prompt, principal, body, parent_version_id=parent, number=number, source=source)

    async def list_prompts(self, project: ProjectOut, page: PageParams) -> Page[PromptOut]:
        prompts = await self._repo.prompts(project.id, page)
        latest = await self._repo.latest_versions([prompt.id for prompt in prompts])
        items = [
            PromptOut(
                id=p.id,
                project_id=p.project_id,
                name=p.name,
                created_at=p.created_at,
                latest_version=version_out(latest[p.id]),
            )
            for p in prompts
        ]
        return to_page(items, page, lambda item: item.id)

    async def get_prompt(self, project: ProjectOut, prompt_id: uuid.UUID) -> PromptOut:
        prompt = await self._prompt(project.id, prompt_id)
        latest = (await self._repo.latest_versions([prompt.id]))[prompt.id]
        return PromptOut(
            id=prompt.id,
            project_id=prompt.project_id,
            name=prompt.name,
            created_at=prompt.created_at,
            latest_version=version_out(latest),
        )

    async def list_versions(
        self, project: ProjectOut, prompt_id: uuid.UUID, page: PageParams
    ) -> Page[PromptVersionOut]:
        prompt = await self._prompt(project.id, prompt_id)
        rows = await self._repo.versions(prompt.id, page)
        return to_page([version_out(row) for row in rows], page, lambda item: item.id)

    async def get_version(self, project_id: uuid.UUID, version_id: uuid.UUID) -> PromptVersionOut:
        return version_out(await self._version(project_id, version_id))

    async def render_version(
        self, project_id: uuid.UUID, version_id: uuid.UUID, inputs: dict[str, Any]
    ) -> RenderedPrompt:
        version = await self._version(project_id, version_id)
        messages = render(version.system_template, version.user_template, inputs)
        return RenderedPrompt(shape=analyze(version.system_template, version.user_template).shape, messages=messages)

    async def check(self, project: ProjectOut, version_id: uuid.UUID, body: CheckRequest) -> PromptCheck:
        version = await self._version(project.id, version_id)
        templates = PromptTemplates(system_template=version.system_template, user_template=version.user_template)
        max_tokens = version.default_params.get("max_tokens")
        return await self._check(
            project.id, templates, body.columns, body.sample_inputs, body.model_profile_ids, max_tokens
        )

    async def inspect(self, project: ProjectOut, body: InspectRequest) -> InspectOut:
        self._check_lengths(body)
        check = await self._check(
            project.id, body, body.columns, body.sample_inputs, body.model_profile_ids, body.max_tokens
        )
        preview = None
        if body.sample_inputs is not None and not missing_inputs(check.required_inputs, list(body.sample_inputs)):
            messages = render(body.system_template, body.user_template, body.sample_inputs)
            preview = RenderedPrompt(shape=check.shape, messages=messages)
        return InspectOut(check=check, preview=preview)

    async def _check(
        self,
        project_id: uuid.UUID,
        templates: PromptTemplates,
        columns: list[str] | None,
        sample_inputs: dict[str, Any] | None,
        model_profile_ids: list[uuid.UUID] | None,
        max_tokens: int | None,
    ) -> PromptCheck:
        info = analyze(templates.system_template, templates.user_template)
        available = columns if columns is not None else list(sample_inputs or {})
        missing = missing_inputs(info.required_inputs, available) if columns is not None or sample_inputs else []
        inputs = dict.fromkeys(info.required_inputs, "") | (sample_inputs or {})
        messages = render(templates.system_template, templates.user_template, inputs)
        profiles = await self._registry.profiles(project_id, model_profile_ids)
        fits = context_fits(messages, profiles, max_tokens, self._settings.token_estimate_chars_per_token)
        return PromptCheck(
            shape=info.shape,
            variables=info.variables,
            required_inputs=info.required_inputs,
            missing_inputs=missing,
            context=fits,
            ok=not missing and all(fit.fits is not False for fit in fits),
        )

    async def _save(
        self,
        prompt: Prompt,
        principal: Principal | None,
        body: PromptCreate | PromptVersionCreate,
        parent_version_id: uuid.UUID | None,
        number: int,
        source: PromptSource = PromptSource.MANUAL,
    ) -> PromptVersionOut:
        self._check_lengths(body)
        self._check_params(body.default_params)
        info: TemplateInfo = analyze(body.system_template, body.user_template)
        version = PromptVersion(
            prompt_id=prompt.id,
            version=number,
            parent_version_id=parent_version_id,
            system_template=body.system_template,
            user_template=body.user_template,
            variables=info.variables,
            default_params=body.default_params,
            source=source,
            change_reason=body.change_reason,
            created_by=principal.user_id if principal else None,
        )
        await self._repo.add(version)
        return version_out(version)

    def _check_lengths(self, templates: PromptTemplates) -> None:
        limit = self._settings.prompt_template_max_chars
        for label, template in (("system", templates.system_template), ("user", templates.user_template)):
            if template is not None and len(template) > limit:
                raise ValidationFailed(TOO_LONG.format(label=label, length=len(template), limit=limit))

    def _check_params(self, params: dict[str, Any]) -> None:
        known = self._registry.tunable_parameters()
        unknown = sorted(set(params) - known)
        if unknown:
            raise ValidationFailed(UNKNOWN_PARAMS.format(names=", ".join(unknown), known=", ".join(sorted(known))))

    async def _prompt(self, project_id: uuid.UUID, prompt_id: uuid.UUID, lock: bool = False) -> Prompt:
        prompt = await self._repo.prompt(project_id, prompt_id, lock=lock)
        if prompt is None:
            raise NotFound(PROMPT_NOT_FOUND)
        return prompt

    async def _version(self, project_id: uuid.UUID, version_id: uuid.UUID) -> PromptVersion:
        version = await self._repo.version(project_id, version_id)
        if version is None:
            raise NotFound(VERSION_NOT_FOUND)
        return version
