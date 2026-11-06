"""
The workspace key store and guardrails (ADR 0030).

A key is entered once for the workspace and then used by any number of its projects. Using it in a project makes
an ordinary project credential that points at the workspace key, so every model call keeps working through the
same path. Rotating the key checks the new key with the provider first (a rejected key changes nothing), then
rewrites the stored key of the workspace entry and of every project that uses it in one transaction: from then on
the old key is used nowhere. Moving a project's own key to the store finds the same key in the workspace's other
projects (exact match after decryption) and links them all. Taking a key out of one project keeps that project's
own copy, which no longer changes with rotation. App credentials are per project and never go here.
"""

import uuid
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import Container
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.security import Principal, utcnow
from app.modules.audit.schemas import AuditAction
from app.modules.audit.service import AuditLog
from app.modules.gateway.repository import LLMCallRepository
from app.modules.organizations.domain import limit_reached, month_start, percent_used
from app.modules.organizations.models import OrganizationKey
from app.modules.organizations.repository import OrganizationRepository
from app.modules.organizations.schemas import (
    GuardrailsOut,
    GuardrailsUpdate,
    KeyProjectOut,
    OrgKeyCreate,
    OrgKeyOut,
    OrgKeyUpdate,
)
from app.modules.projects.repository import ProjectRepository
from app.modules.projects.schemas import ProjectOut
from app.modules.registry.domain import key_last4
from app.modules.registry.repository import RegistryRepository
from app.modules.registry.schemas import CredentialCreate
from app.modules.registry.service import RegistryService

KEY_NOT_FOUND = "This key doesn't exist in this workspace."
PROJECT_NOT_IN_WORKSPACE = "That project isn't in this workspace."
IN_USE = "This key is used in {names}. Take it out of those projects first, or rotate it instead."
ALREADY_USED = "This key is already used in {project}."
NO_STORED_KEY = "This key has no secret to move (it needs none)."
APP_KEYS = "App connections stay with their project and can't be moved to the workspace."


class OrganizationService:
    def __init__(
        self,
        session: AsyncSession,
        container: Container,
        registry: RegistryService,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._session = session
        self._repo = OrganizationRepository(session)
        self._registry_repo = RegistryRepository(session)
        self._projects = ProjectRepository(session)
        self._registry = registry
        self._audit = AuditLog(session, container.settings)
        self._clock = clock

    # --- keys --------------------------------------------------------------------------------------

    async def keys(self, organization_id: uuid.UUID) -> list[OrgKeyOut]:
        return [await self._out(row) for row in await self._repo.keys(organization_id)]

    async def create_key(self, actor: Principal, organization_id: uuid.UUID, body: OrgKeyCreate) -> OrgKeyOut:
        api_key = body.api_key.get_secret_value().strip() if body.api_key else None
        if not api_key:
            raise ValidationFailed("Paste the API key to store.")
        await self._registry.check_key(body.provider, api_key, body.base_url)
        row = await self._repo.add_key(
            OrganizationKey(
                organization_id=organization_id,
                provider=body.provider,
                label=body.label,
                encrypted_key=self._registry.encrypt_key(api_key),
                key_last4=key_last4(api_key),
                base_url=body.base_url,
                rpm_limit=body.rpm_limit,
                tpm_limit=body.tpm_limit,
                created_by=actor.user_id,
            )
        )
        await self._audit.record(
            organization_id=organization_id,
            actor_id=actor.user_id,
            action=AuditAction.KEY_ADDED,
            summary=f"Added a {body.provider} key (ending {row.key_last4}) to the workspace key store.",
            target_type="organization_key",
            target_id=row.id,
            details={"provider": body.provider, "key_last4": row.key_last4},
        )
        return await self._out(row)

    async def update_key(
        self, actor: Principal, organization_id: uuid.UUID, key_id: uuid.UUID, body: OrgKeyUpdate
    ) -> OrgKeyOut:
        row = await self._key(organization_id, key_id)
        changes = body.model_dump(exclude_unset=True)
        for name, value in changes.items():
            setattr(row, name, value)
        for credential, _, _ in await self._registry_repo.credentials_of_key(row.id):
            for name, value in changes.items():
                setattr(credential, name, value)
        await self._audit.record(
            organization_id=organization_id,
            actor_id=actor.user_id,
            action=AuditAction.KEY_ADDED,
            summary=f"Changed the settings of the workspace {row.provider} key ending {row.key_last4}.",
            target_type="organization_key",
            target_id=row.id,
            details={"changed": sorted(changes)},
        )
        return await self._out(row)

    async def rotate_key(
        self, actor: Principal, organization_id: uuid.UUID, key_id: uuid.UUID, new_key: str
    ) -> OrgKeyOut:
        row = await self._key(organization_id, key_id, for_update=True)
        new_key = new_key.strip()
        if not new_key:
            raise ValidationFailed("Paste the new API key.")
        await self._registry.check_key(row.provider, new_key, row.base_url)  # a rejected key changes nothing
        now = self._clock()
        old_last4 = row.key_last4
        row.encrypted_key = self._registry.encrypt_key(new_key)
        row.key_last4 = key_last4(new_key)
        row.rotated_at = now
        updated = await self._registry_repo.rewrite_key_of(row.id, row.encrypted_key, row.key_last4, now)
        used_in = await self._used_in(row.id)
        await self._audit.record(
            organization_id=organization_id,
            actor_id=actor.user_id,
            action=AuditAction.KEY_ROTATED,
            summary=(
                f"Rotated the workspace {row.provider} key (ending {old_last4} to {row.key_last4}); "
                f"{updated} project{'s' if updated != 1 else ''} now use the new key."
            ),
            target_type="organization_key",
            target_id=row.id,
            details={
                "provider": row.provider,
                "old_key_last4": old_last4,
                "key_last4": row.key_last4,
                "projects": [p.project_name for p in used_in],
            },
        )
        return await self._out(row)

    async def delete_key(self, actor: Principal, organization_id: uuid.UUID, key_id: uuid.UUID) -> None:
        row = await self._key(organization_id, key_id, for_update=True)
        used_in = await self._used_in(row.id)
        if used_in:
            raise Conflict(IN_USE.format(names=", ".join(p.project_name for p in used_in)))
        await self._repo.delete_key(row.id)
        await self._audit.record(
            organization_id=organization_id,
            actor_id=actor.user_id,
            action=AuditAction.KEY_REMOVED,
            summary=f"Removed the workspace {row.provider} key ending {row.key_last4}.",
            target_type="organization_key",
            target_id=row.id,
            details={"provider": row.provider, "key_last4": row.key_last4},
        )

    async def attach(
        self, actor: Principal, organization_id: uuid.UUID, key_id: uuid.UUID, project_id: uuid.UUID
    ) -> OrgKeyOut:
        """Use the workspace key in a project: the project gets a credential that follows the key."""
        row = await self._key(organization_id, key_id)
        project = await self._project(organization_id, project_id)
        for _, name, used_project in await self._registry_repo.credentials_of_key(row.id):
            if used_project == project.id:
                raise Conflict(ALREADY_USED.format(project=name))
        body = CredentialCreate(
            provider=row.provider,
            api_key=SecretStr(self._registry.decrypt_key(row.encrypted_key)),
            base_url=row.base_url,
            label=row.label,
            rpm_limit=row.rpm_limit,
            tpm_limit=row.tpm_limit,
        )
        await self._registry.add_credential(project, actor, body, organization_key_id=row.id)
        return await self._out(row)

    async def detach(
        self, actor: Principal, organization_id: uuid.UUID, key_id: uuid.UUID, project_id: uuid.UUID
    ) -> OrgKeyOut:
        """Stop a project following the key: it keeps its own copy as it is now."""
        row = await self._key(organization_id, key_id)
        project = await self._project(organization_id, project_id)
        linked = [c for c, _, used in await self._registry_repo.credentials_of_key(row.id) if used == project.id]
        if not linked:
            raise NotFound("This project doesn't use this key.")
        for credential in linked:
            credential.organization_key_id = None
        await self._audit.record(
            organization_id=organization_id,
            project_id=project.id,
            actor_id=actor.user_id,
            action=AuditAction.KEY_DETACHED,
            summary=f"{project.name} no longer follows the workspace {row.provider} key ending {row.key_last4}.",
            target_type="organization_key",
            target_id=row.id,
        )
        return await self._out(row)

    async def promote(
        self, actor: Principal, organization_id: uuid.UUID, project_id: uuid.UUID, credential_id: uuid.UUID
    ) -> OrgKeyOut:
        """Move a project's own key to the workspace store. The same key in the workspace's other projects (found by
        comparing the decrypted keys) is linked too, so rotating it later changes all of them. Nothing stops working."""
        project = await self._project(organization_id, project_id)
        source = await self._registry_repo.credential(project.id, credential_id)
        if source is None:
            raise NotFound("This key doesn't exist in this project.")
        if source.provider == "app":
            raise ValidationFailed(APP_KEYS)
        if source.encrypted_key is None:
            raise ValidationFailed(NO_STORED_KEY)
        if source.organization_key_id is not None:
            raise Conflict("This key is already in the workspace key store.")
        plain = self._registry.decrypt_key(source.encrypted_key)
        row = await self._repo.add_key(
            OrganizationKey(
                organization_id=organization_id,
                provider=source.provider,
                label=source.label,
                encrypted_key=source.encrypted_key,
                key_last4=source.key_last4,
                base_url=source.base_url,
                rpm_limit=source.rpm_limit,
                tpm_limit=source.tpm_limit,
                created_by=actor.user_id,
            )
        )
        linked = 0
        for candidate in await self._registry_repo.credentials_in_organization(organization_id):
            same = (
                candidate.provider == source.provider
                and (candidate.base_url or None) == (source.base_url or None)
                and candidate.encrypted_key is not None
                and self._registry.decrypt_key(candidate.encrypted_key) == plain
            )
            if same:
                candidate.organization_key_id = row.id
                linked += 1
        await self._audit.record(
            organization_id=organization_id,
            project_id=project.id,
            actor_id=actor.user_id,
            action=AuditAction.KEY_ADDED,
            summary=(
                f"Moved the {source.provider} key ending {source.key_last4} to the workspace key store; "
                f"{linked} project key{'s' if linked != 1 else ''} now follow it."
            ),
            target_type="organization_key",
            target_id=row.id,
            details={"provider": source.provider, "key_last4": source.key_last4, "linked": linked},
        )
        return await self._out(row)

    # --- guardrails --------------------------------------------------------------------------------

    async def guardrails(self, organization_id: uuid.UUID) -> GuardrailsOut:
        now = self._clock()
        limit = await self._repo.limit(organization_id)
        since = month_start(now)
        project_ids = await self._projects.ids_in_organization(organization_id)
        spent = await LLMCallRepository(self._session).spent_since(project_ids, since)
        return GuardrailsOut(
            monthly_spend_limit=limit,
            spent_this_month=spent,
            month_started_at=since,
            percent_used=percent_used(spent, limit),
            limit_reached=limit_reached(spent, limit),
        )

    async def set_guardrails(
        self, actor: Principal, organization_id: uuid.UUID, body: GuardrailsUpdate
    ) -> GuardrailsOut:
        before = await self._repo.limit(organization_id)
        await self._repo.set_limit(organization_id, body.monthly_spend_limit, actor.user_id)
        await self._audit.record(
            organization_id=organization_id,
            actor_id=actor.user_id,
            action=AuditAction.LIMIT_CHANGED,
            summary=_limit_summary(before, body.monthly_spend_limit),
            target_type="organization",
            target_id=organization_id,
            details={
                "from": None if before is None else str(before),
                "to": None if body.monthly_spend_limit is None else str(body.monthly_spend_limit),
            },
        )
        return await self.guardrails(organization_id)

    # --- helpers -----------------------------------------------------------------------------------

    async def _key(self, organization_id: uuid.UUID, key_id: uuid.UUID, for_update: bool = False) -> OrganizationKey:
        row = await self._repo.key(organization_id, key_id, for_update)
        if row is None:
            raise NotFound(KEY_NOT_FOUND)
        return row

    async def _project(self, organization_id: uuid.UUID, project_id: uuid.UUID) -> ProjectOut:
        project = await self._projects.get_in(project_id, [organization_id])
        if project is None:
            raise NotFound(PROJECT_NOT_IN_WORKSPACE)
        return ProjectOut.model_validate(project)

    async def _used_in(self, key_id: uuid.UUID) -> list[KeyProjectOut]:
        return [
            KeyProjectOut(project_id=project_id, project_name=name)
            for _, name, project_id in await self._registry_repo.credentials_of_key(key_id)
        ]

    async def _out(self, row: OrganizationKey) -> OrgKeyOut:
        return OrgKeyOut(
            id=row.id,
            provider=row.provider,
            label=row.label,
            key_last4=row.key_last4,
            base_url=row.base_url,
            rpm_limit=row.rpm_limit,
            tpm_limit=row.tpm_limit,
            created_at=row.created_at,
            rotated_at=row.rotated_at,
            used_in=await self._used_in(row.id),
        )


def _limit_summary(before: Decimal | None, after: Decimal | None) -> str:
    if after is None:
        return "Removed the monthly spending limit."
    if before is None:
        return f"Set the monthly spending limit to ${after:.2f}."
    return f"Changed the monthly spending limit from ${before:.2f} to ${after:.2f}."
