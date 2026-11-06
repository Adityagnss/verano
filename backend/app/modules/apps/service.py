"""
Apps use cases (ADR 0024): add, list, change, remove and try an app target.

An app target is stored as a credential of the provider `app` (its headers encrypted like a provider key) and
one model profile, so the planner, the executor and the results handle it as one more model column, plus an
`app_targets` row with what is specific to an app. The credential is hidden from the Keys list. Secrets are
accepted once and never returned; only the header names are shown.
"""

import json
import uuid
from base64 import b64encode
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.container import Container
from app.core.errors import NotFound, ValidationFailed
from app.core.security import Principal, SecretBox
from app.modules.apps.mapping import ResponseMapping
from app.modules.apps.models import AppTarget
from app.modules.apps.repository import AppRepository
from app.modules.apps.runner import AppCallResult, AppRunner, AppSpec
from app.modules.apps.schemas import (
    AppMode,
    AppReplyOut,
    AppTargetCreate,
    AppTargetOut,
    AppTargetUpdate,
    AppTestOut,
    AuthKind,
)
from app.modules.projects.schemas import ProjectOut
from app.modules.registry.models import ModelProfile, ProviderCredential
from app.modules.registry.schemas import CredentialStatus, PriceSource

APP_PROVIDER = "app"
NOT_FOUND = "This app doesn't exist in this project."
NEEDS_BEARER = "Bearer authentication needs a token."
NEEDS_BASIC = "Basic authentication needs a username and a password."
NEEDS_HEADERS = "Header authentication needs at least one header."


def spec_of(target: AppTarget) -> AppSpec:
    return AppSpec(
        url=target.url,
        method=target.method,
        request_template=target.request_template,
        mapping=ResponseMapping(
            answer_path=target.answer_path,
            chunks_path=target.chunks_path,
            tool_calls_path=target.tool_calls_path,
            cost_path=target.cost_path,
        ),
        timeout_s=target.timeout_s,
        retries=target.retries,
    )


def target_out(target: AppTarget) -> AppTargetOut:
    return AppTargetOut(
        id=target.id,
        credential_id=target.credential_id,
        model_profile_id=target.model_profile_id,
        name=target.name,
        url=target.url,
        method=target.method,
        mode=AppMode(target.mode),
        request_template=target.request_template,
        answer_path=target.answer_path,
        chunks_path=target.chunks_path,
        tool_calls_path=target.tool_calls_path,
        cost_path=target.cost_path,
        auth_kind=AuthKind(target.auth_kind),
        header_names=[str(name) for name in target.header_names],
        timeout_s=target.timeout_s,
        concurrency=target.concurrency,
        retries=target.retries,
    )


def build_headers(
    kind: AuthKind,
    bearer: str | None,
    username: str | None,
    password: str | None,
    extra: dict[str, str],
) -> dict[str, str]:
    """The headers to send, built from the chosen sign-in kind. Raises a message that says what is missing."""
    headers = dict(extra)
    if kind is AuthKind.BEARER:
        if not bearer:
            raise ValidationFailed(NEEDS_BEARER)
        headers["Authorization"] = f"Bearer {bearer}"
    elif kind is AuthKind.BASIC:
        if not username or password is None:
            raise ValidationFailed(NEEDS_BASIC)
        headers["Authorization"] = "Basic " + b64encode(f"{username}:{password}".encode()).decode()
    elif kind is AuthKind.HEADERS and not headers:
        raise ValidationFailed(NEEDS_HEADERS)
    return headers


class AppService:
    def __init__(self, session: AsyncSession, container: Container) -> None:
        self._session = session
        self._repo = AppRepository(session)
        self._settings: Settings = container.settings
        self._secrets: SecretBox = container.secret_box
        self._runner = AppRunner(container.settings)

    async def create(self, project: ProjectOut, principal: Principal, body: AppTargetCreate) -> AppTargetOut:
        headers = build_headers(
            body.auth_kind,
            body.bearer_token.get_secret_value() if body.bearer_token else None,
            body.basic_username,
            body.basic_password.get_secret_value() if body.basic_password else None,
            {name: value.get_secret_value() for name, value in body.headers.items()},
        )
        credential = await self._repo.add(
            ProviderCredential(
                project_id=project.id,
                provider=APP_PROVIDER,
                label=body.name,
                encrypted_key=self._secrets.encrypt(json.dumps(headers)),
                key_last4=None,
                base_url=body.url,
                status=CredentialStatus.VALID,
                created_by=principal.user_id,
            )
        )
        profile = await self._repo.add(
            ModelProfile(
                project_id=project.id,
                credential_id=credential.id,
                provider=APP_PROVIDER,
                model_name=body.name,
                display_name=body.name,
                litellm_model=f"{APP_PROVIDER}/{credential.id}",
                context_window=None,
                max_output_tokens=None,
                parameters={},
                supports_json_mode=False,
                supports_system_prompt=False,
                input_price_per_mtok=None,
                output_price_per_mtok=None,
                price_source=PriceSource.UNKNOWN,
                is_selected=True,
            )
        )
        settings = self._settings
        target = await self._repo.add(
            AppTarget(
                project_id=project.id,
                credential_id=credential.id,
                model_profile_id=profile.id,
                name=body.name,
                url=body.url,
                method=body.method,
                mode=body.mode.value,
                request_template=body.request_template,
                answer_path=body.answer_path,
                chunks_path=body.chunks_path,
                tool_calls_path=body.tool_calls_path,
                cost_path=body.cost_path,
                auth_kind=body.auth_kind.value,
                header_names=sorted(headers),
                timeout_s=body.timeout_s or settings.app_timeout_s,
                concurrency=body.concurrency or settings.app_concurrency,
                retries=settings.app_retry_attempts if body.retries is None else body.retries,
            )
        )
        return target_out(target)

    async def list(self, project_id: uuid.UUID) -> list[AppTargetOut]:
        return [target_out(t) for t in await self._repo.targets(project_id)]

    async def get(self, project_id: uuid.UUID, target_id: uuid.UUID) -> AppTargetOut:
        return target_out(await self._target(project_id, target_id))

    async def update(self, project_id: uuid.UUID, target_id: uuid.UUID, body: AppTargetUpdate) -> AppTargetOut:
        target = await self._target(project_id, target_id)
        changes = body.model_dump(
            exclude_unset=True, exclude={"auth_kind", "bearer_token", "basic_username", "basic_password", "headers"}
        )
        for name, value in changes.items():
            setattr(target, name, value.value if hasattr(value, "value") else value)
        credential = await self._repo.credential(target.credential_id)
        if credential is not None:
            if body.url is not None:
                credential.base_url = body.url
            if body.name is not None:
                credential.label = body.name
        profile = await self._repo.profile(target.model_profile_id)
        if profile is not None and body.name is not None:
            profile.display_name = body.name
            profile.model_name = body.name
        if _wants_new_secrets(body) and credential is not None:
            kind = body.auth_kind or AuthKind(target.auth_kind)
            headers = build_headers(
                kind,
                body.bearer_token.get_secret_value() if body.bearer_token else None,
                body.basic_username,
                body.basic_password.get_secret_value() if body.basic_password else None,
                {name: v.get_secret_value() for name, v in (body.headers or {}).items()},
            )
            credential.encrypted_key = self._secrets.encrypt(json.dumps(headers))
            target.auth_kind = kind.value
            target.header_names = sorted(headers)
        await self._session.flush()
        return target_out(target)

    async def delete(self, project_id: uuid.UUID, target_id: uuid.UUID) -> None:
        target = await self._target(project_id, target_id)
        credential = await self._repo.credential(target.credential_id)
        if credential is not None:
            await self._repo.delete(credential)

    async def test(self, project_id: uuid.UUID, target_id: uuid.UUID, inputs: dict[str, Any]) -> AppTestOut:
        """Sends one test case and shows exactly what went out and came back, so the mapping can be fixed
        before a run. Nothing is stored."""
        target = await self._target(project_id, target_id)
        result = await self._runner.call(spec_of(target), await self.headers(target), inputs)
        return test_out(result)

    async def headers(self, target: AppTarget) -> dict[str, str]:
        credential = await self._repo.credential(target.credential_id)
        if credential is None or credential.encrypted_key is None:
            return {}
        loaded = json.loads(self._secrets.decrypt(credential.encrypted_key))
        return {str(k): str(v) for k, v in loaded.items()}

    async def _target(self, project_id: uuid.UUID, target_id: uuid.UUID) -> AppTarget:
        target = await self._repo.target(project_id, target_id)
        if target is None:
            raise NotFound(NOT_FOUND)
        return target


def _wants_new_secrets(body: AppTargetUpdate) -> bool:
    return any(
        value is not None
        for value in (body.auth_kind, body.bearer_token, body.basic_username, body.basic_password, body.headers)
    )


def test_out(result: AppCallResult) -> AppTestOut:
    reply = result.reply
    return AppTestOut(
        request_body=result.request_body,
        status_code=result.status_code,
        response_body=result.response_body,
        truncated=result.truncated,
        latency_ms=result.latency_ms,
        reply=AppReplyOut(answer=reply.answer, chunks=reply.chunks, tool_calls=reply.tool_calls, cost=reply.cost)
        if reply
        else None,
        error=result.error,
    )
