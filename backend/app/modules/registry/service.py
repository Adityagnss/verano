"""
Registry use cases: provider catalog, credentials, discovery, selection and call targets.

Adding a credential lists the provider's models with the key, which both validates the
key (a rejected key fails immediately with a clear message and nothing is stored) and
discovers the models, in one request that spends no tokens. Only chat-capable models are
kept, each with a profile built by `domain.build_profile`. The plaintext key exists only
inside `call_target`, which the gateway calls for each LLM call.
"""

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.container import Container
from app.core.datafiles import load_yaml
from app.core.errors import NotFound, ProviderAuthError, ValidationFailed
from app.core.pagination import Page, PageParams, to_page
from app.core.registry import load_plugins
from app.core.security import Principal, SecretBox, utcnow
from app.modules.projects.schemas import ProjectOut
from app.modules.registry.domain import build_profile, is_chat_model, key_last4, litellm_model
from app.modules.registry.models import ModelProfile, ProviderCredential
from app.modules.registry.plugins.base import PROVIDER_CLIENTS, BaseProviderClient
from app.modules.registry.plugins.litellm_metadata import lookup_metadata
from app.modules.registry.repository import RegistryRepository
from app.modules.registry.schemas import (
    CallTarget,
    CredentialCreate,
    CredentialOut,
    CredentialStatus,
    CredentialUpdate,
    ModelMetadata,
    ModelOverrides,
    ModelProfileOut,
    ModelSelection,
    PriceSource,
    ProviderCatalog,
    ProviderOut,
    ProviderSpec,
    RateLimitHeaders,
    RawModel,
)

load_plugins("app.modules.registry.plugins")

CREDENTIAL_NOT_FOUND = "This key doesn't exist in this project."
MODEL_NOT_FOUND = "The model '{model}' isn't available for this key. Refresh the model list and try again."
KEY_REQUIRED = "{provider} needs an API key."
UNKNOWN_PROVIDER = "Unknown provider '{provider}'."

MetadataLookup = Callable[[str], ModelMetadata | None]


def profile_out(row: ModelProfile) -> ModelProfileOut:
    return ModelProfileOut.model_validate(
        {
            **{column: getattr(row, column) for column in ModelProfileOut.model_fields if hasattr(row, column)},
            "price_known": row.price_source is not PriceSource.UNKNOWN,
        }
    )


def credential_out(row: ProviderCredential, model_count: int) -> CredentialOut:
    return CredentialOut.model_validate(
        {
            **{column: getattr(row, column) for column in CredentialOut.model_fields if hasattr(row, column)},
            "model_count": model_count,
        }
    )


class RegistryService:
    def __init__(
        self,
        session: AsyncSession,
        container: Container,
        metadata: MetadataLookup = lookup_metadata,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._session = session
        self._repo = RegistryRepository(session)
        self._settings: Settings = container.settings
        self._secrets: SecretBox = container.secret_box
        self._http = container.http
        self._metadata = metadata
        self._clock = clock
        self.catalog = load_yaml(self._settings.providers_path, ProviderCatalog)
        self._overrides = load_yaml(self._settings.model_overrides_path, ModelOverrides)

    def providers(self) -> list[ProviderOut]:
        return [
            ProviderOut(
                name=name,
                display_name=spec.display_name,
                requires_key=spec.requires_key,
                default_base_url=self._default_base_url(spec),
                free=spec.free,
            )
            for name, spec in self.catalog.providers.items()
            if self._enabled(spec)
        ]

    def rate_limit_headers(self) -> RateLimitHeaders:
        return self.catalog.rate_limit_headers

    async def add_credential(self, project: ProjectOut, principal: Principal, body: CredentialCreate) -> CredentialOut:
        spec = self._spec(body.provider)
        api_key = body.api_key.get_secret_value().strip() if body.api_key else None
        if spec.requires_key and not api_key:
            raise ValidationFailed(KEY_REQUIRED.format(provider=spec.display_name))
        base_url = body.base_url or self._default_base_url(spec) or ""
        raw_models = await self._client(spec).list_models(api_key, base_url)
        credential = await self._repo.add_credential(
            ProviderCredential(
                project_id=project.id,
                provider=body.provider,
                label=body.label,
                encrypted_key=self._secrets.encrypt(api_key) if api_key else None,
                key_last4=key_last4(api_key) if api_key else None,
                base_url=body.base_url,
                status=CredentialStatus.VALID,
                rpm_limit=body.rpm_limit,
                tpm_limit=body.tpm_limit,
                last_validated_at=self._clock(),
                created_by=principal.user_id,
            )
        )
        count = await self._store_profiles(credential, spec, raw_models)
        return credential_out(credential, count)

    async def list_credentials(self, project: ProjectOut) -> list[CredentialOut]:
        return [credential_out(row, n) for row, n in await self._repo.credentials_with_counts(project.id)]

    async def update_credential(
        self, project: ProjectOut, credential_id: uuid.UUID, body: CredentialUpdate
    ) -> CredentialOut:
        credential = await self._credential(project.id, credential_id)
        await self._repo.update_credential(credential.id, body.model_dump(exclude_unset=True))
        await self._session.refresh(credential)
        return credential_out(credential, await self._repo.model_count(credential.id))

    async def delete_credential(self, project: ProjectOut, credential_id: uuid.UUID) -> None:
        credential = await self._credential(project.id, credential_id)
        await self._repo.delete_credential(credential.id)

    async def refresh_models(self, project: ProjectOut, credential_id: uuid.UUID) -> CredentialOut:
        credential = await self._credential(project.id, credential_id)
        spec = self._spec(credential.provider)
        raw_models = await self._checked(credential, self._client(spec).list_models)
        count = await self._store_profiles(credential, spec, raw_models)
        return credential_out(credential, count)

    async def validate_credential(self, project: ProjectOut, credential_id: uuid.UUID) -> CredentialOut:
        credential = await self._credential(project.id, credential_id)
        await self._checked(credential, self._client(self._spec(credential.provider)).validate)
        return credential_out(credential, await self._repo.model_count(credential.id))

    async def list_models(
        self, project: ProjectOut, page: PageParams, selected_only: bool, credential_id: uuid.UUID | None
    ) -> Page[ModelProfileOut]:
        rows = await self._repo.profiles(project.id, page, selected_only, credential_id)
        return to_page([profile_out(row) for row in rows], page, lambda p: p.id)

    async def select_models(self, project: ProjectOut, selection: ModelSelection) -> None:
        await self._repo.set_selected(project.id, selection.selected, True)
        await self._repo.set_selected(project.id, selection.unselected, False)

    async def call_target(self, project_id: uuid.UUID, credential_id: uuid.UUID, model_name: str) -> CallTarget:
        credential = await self._credential(project_id, credential_id)
        profile = await self._repo.profile_by_name(credential.id, model_name)
        if profile is None:
            raise NotFound(MODEL_NOT_FOUND.format(model=model_name))
        spec = self._spec(credential.provider)
        return CallTarget(
            credential_id=credential.id,
            provider=credential.provider,
            provider_display_name=spec.display_name,
            api_key=self._decrypted(credential),
            api_base=credential.base_url or self._default_base_url(spec),
            profile=profile_out(profile),
            default_limits=spec.rate_limits,
            override_rpm=credential.rpm_limit,
            override_tpm=credential.tpm_limit,
        )

    async def _checked(self, credential: ProviderCredential, call: Callable[[str | None, str], Any]) -> Any:
        spec = self._spec(credential.provider)
        base_url = credential.base_url or self._default_base_url(spec) or ""
        try:
            result = await call(self._plain_key(credential), base_url)
        except ProviderAuthError as exc:
            await self._mark(credential, CredentialStatus.INVALID, exc.message)
            await self._session.commit()
            raise
        await self._mark(credential, CredentialStatus.VALID, None)
        return result

    async def _mark(self, credential: ProviderCredential, status: CredentialStatus, message: str | None) -> None:
        values = {"status": status, "status_message": message, "last_validated_at": self._clock()}
        await self._repo.update_credential(credential.id, values)
        await self._session.refresh(credential)

    async def _store_profiles(
        self, credential: ProviderCredential, spec: ProviderSpec, raw_models: list[RawModel]
    ) -> int:
        rows = [self._profile_row(credential, spec, raw) for raw in raw_models]
        chat_rows = [row for row in rows if row is not None]
        await self._repo.upsert_profiles(chat_rows, self._clock())
        await self._repo.delete_profiles_not_in(credential.id, [row["model_name"] for row in chat_rows])
        return len(chat_rows)

    def _profile_row(self, credential: ProviderCredential, spec: ProviderSpec, raw: RawModel) -> dict[str, Any] | None:
        model = litellm_model(spec, raw.id)
        metadata = self._metadata(model)
        if not is_chat_model(raw, spec, metadata):
            return None
        draft = build_profile(self.catalog, spec, raw, metadata, self._overrides.models.get(model))
        return {
            **draft.model_dump(mode="python"),
            "parameters": {k: v.model_dump() for k, v in draft.parameters.items()},
            "project_id": credential.project_id,
            "credential_id": credential.id,
            "provider": credential.provider,
        }

    async def _credential(self, project_id: uuid.UUID, credential_id: uuid.UUID) -> ProviderCredential:
        credential = await self._repo.credential(project_id, credential_id)
        if credential is None:
            raise NotFound(CREDENTIAL_NOT_FOUND)
        return credential

    def _plain_key(self, credential: ProviderCredential) -> str | None:
        return self._secrets.decrypt(credential.encrypted_key) if credential.encrypted_key else None

    def _decrypted(self, credential: ProviderCredential) -> SecretStr | None:
        key = self._plain_key(credential)
        return SecretStr(key) if key else None

    def _spec(self, provider: str) -> ProviderSpec:
        spec = self.catalog.providers.get(provider)
        if spec is None or not self._enabled(spec):
            raise ValidationFailed(UNKNOWN_PROVIDER.format(provider=provider))
        return spec

    def _enabled(self, spec: ProviderSpec) -> bool:
        return spec.enabled_setting is None or bool(getattr(self._settings, spec.enabled_setting))

    def _default_base_url(self, spec: ProviderSpec) -> str | None:
        return spec.base_url or (str(getattr(self._settings, spec.base_url_setting)) if spec.base_url_setting else None)

    def _client(self, spec: ProviderSpec) -> BaseProviderClient:
        return PROVIDER_CLIENTS[spec.client](spec, self._http, settings=self._settings)
