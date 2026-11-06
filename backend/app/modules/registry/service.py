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
from app.modules.audit.schemas import AuditAction
from app.modules.audit.service import AuditLog
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
    SharedCredentialOut,
)

load_plugins("app.modules.registry.plugins")

CREDENTIAL_NOT_FOUND = "This key doesn't exist in this project."
MODEL_NOT_FOUND = "The model '{model}' isn't available for this key. Refresh the model list and try again."
KEY_REQUIRED = "{provider} needs an API key."
ALL_MODELS = 5000
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
        self._audit = AuditLog(session, container.settings)
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

    async def check_key(self, provider: str, api_key: str | None, base_url: str | None) -> None:
        """Refuse a key the provider rejects, before anything is stored (spends no tokens)."""
        spec = self._spec(provider)
        if spec.requires_key and not api_key:
            raise ValidationFailed(KEY_REQUIRED.format(provider=spec.display_name))
        url = base_url or self._default_base_url(spec) or ""
        client = self._client(spec)
        if spec.key_check_path:
            await client.validate(api_key, url)
        await client.list_models(api_key, url)

    def encrypt_key(self, api_key: str) -> bytes:
        return self._secrets.encrypt(api_key)

    def decrypt_key(self, encrypted: bytes) -> str:
        return self._secrets.decrypt(encrypted)

    async def add_credential(
        self,
        project: ProjectOut,
        principal: Principal,
        body: CredentialCreate,
        organization_key_id: uuid.UUID | None = None,
    ) -> CredentialOut:
        spec = self._spec(body.provider)
        api_key = body.api_key.get_secret_value().strip() if body.api_key else None
        if spec.requires_key and not api_key:
            raise ValidationFailed(KEY_REQUIRED.format(provider=spec.display_name))
        base_url = body.base_url or self._default_base_url(spec) or ""
        client = self._client(spec)
        if spec.key_check_path:
            await client.validate(api_key, base_url)
        raw_models = await client.list_models(api_key, base_url)
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
                organization_key_id=organization_key_id,
            )
        )
        count = await self._store_profiles(credential, spec, raw_models)
        await self._audit.record(
            organization_id=project.organization_id,
            project_id=project.id,
            actor_id=principal.user_id,
            action=AuditAction.KEY_ATTACHED if organization_key_id else AuditAction.KEY_ADDED,
            summary=f"Added a {spec.display_name} key (ending {credential.key_last4 or 'none'}) to {project.name}.",
            target_type="credential",
            target_id=credential.id,
            details={"provider": body.provider, "key_last4": credential.key_last4},
        )
        return credential_out(credential, count)

    async def shared_credentials(self, project: ProjectOut) -> list[SharedCredentialOut]:
        """Keys from the organization's other projects that this project does not have yet (same provider and
        same last four characters), so a key is typed once."""
        have = {(c.provider, c.key_last4) for c, _ in await self._repo.credentials_with_counts(project.id)}
        seen: set[tuple[str, str | None]] = set(have)
        out = []
        for row, project_name in await self._repo.credentials_elsewhere(project.organization_id, project.id):
            identity = (row.provider, row.key_last4)
            if identity in seen:
                continue
            seen.add(identity)
            out.append(
                SharedCredentialOut(
                    id=row.id,
                    provider=row.provider,
                    label=row.label,
                    key_last4=row.key_last4,
                    base_url=row.base_url,
                    project_name=project_name,
                )
            )
        return out

    async def copy_credential(
        self, project: ProjectOut, principal: Principal, credential_id: uuid.UUID
    ) -> CredentialOut:
        """Add a key from another project of the organization to this one: it is checked and its models listed like
        a key typed in here."""
        found = next((c for c in await self.shared_credentials(project) if c.id == credential_id), None)
        source = await self._repo.credential_any(credential_id) if found else None
        if source is None or found is None:
            raise NotFound(CREDENTIAL_NOT_FOUND)
        body = CredentialCreate(
            provider=source.provider,
            api_key=self._decrypted(source),
            base_url=source.base_url,
            label=source.label,
            rpm_limit=source.rpm_limit,
            tpm_limit=source.tpm_limit,
        )
        return await self.add_credential(project, principal, body)

    async def list_credentials(self, project: ProjectOut) -> list[CredentialOut]:
        return [credential_out(row, n) for row, n in await self._repo.credentials_with_counts(project.id)]

    async def update_credential(
        self, project: ProjectOut, credential_id: uuid.UUID, body: CredentialUpdate, principal: Principal
    ) -> CredentialOut:
        credential = await self._credential(project.id, credential_id)
        changes = body.model_dump(exclude_unset=True)
        await self._repo.update_credential(credential.id, changes)
        await self._session.refresh(credential)
        await self._audit.record(
            organization_id=project.organization_id,
            project_id=project.id,
            actor_id=principal.user_id,
            action=AuditAction.KEY_ADDED,
            summary=f"Changed the settings of the {credential.provider} key ending {credential.key_last4 or 'none'}.",
            target_type="credential",
            target_id=credential.id,
            details={"changed": sorted(changes)},
        )
        return credential_out(credential, await self._repo.model_count(credential.id))

    async def delete_credential(self, project: ProjectOut, credential_id: uuid.UUID, principal: Principal) -> None:
        credential = await self._credential(project.id, credential_id)
        await self._repo.delete_credential(credential.id)
        await self._audit.record(
            organization_id=project.organization_id,
            project_id=project.id,
            actor_id=principal.user_id,
            action=AuditAction.KEY_REMOVED,
            summary=(
                f"Removed the {credential.provider} key ending {credential.key_last4 or 'none'} from {project.name}."
            ),
            target_type="credential",
            target_id=credential.id,
            details={"provider": credential.provider, "key_last4": credential.key_last4},
        )

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

    async def profiles(self, project_id: uuid.UUID, ids: list[uuid.UUID] | None = None) -> list[ModelProfileOut]:
        return [profile_out(row) for row in await self._repo.profiles_in(project_id, ids)]

    async def all_profiles(self, project_id: uuid.UUID) -> list[ModelProfileOut]:
        """Every discovered model of the project, selected or not (`profiles` without ids is the selected ones)."""
        rows = await self._repo.profiles(project_id, PageParams(limit=ALL_MODELS, cursor=None), False, None)
        return [profile_out(row) for row in rows]

    def tunable_parameters(self) -> set[str]:
        return {*self.catalog.tunable_parameters, self.catalog.json_mode_parameter}

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
