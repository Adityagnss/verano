"""
Prompt labels: which saved version an app gets when it asks for `production`, `staging` or a
custom label.

A label points at one saved version (never an Improve candidate). Every move is written to the
label's history with who made it and why (set by hand, Accept, rollback, removal), so a bad
release is undone in one step: rollback points the label back at the version it came from.
Accept moves a label only when the prompt's "move on accept" setting names one; that setting is
off until the user turns it on. `fetch` is what apps call: one joined query, and an ETag made
from the version id so an unchanged prompt costs a 304.
Used by the prompt service (and through it by Improve's Accept) and by the label routes.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.pagination import Page, PageParams, to_page
from app.core.security import Principal, utcnow
from app.modules.prompts.domain import rollback_target
from app.modules.prompts.label_repository import LabelRepository
from app.modules.prompts.label_schemas import (
    FetchedPrompt,
    LabelMoveOut,
    LabelsOut,
    MoveReason,
    PromptLabelOut,
)
from app.modules.prompts.models import Prompt, PromptLabel, PromptLabelMove, PromptVersion
from app.modules.prompts.repository import PromptRepository

PROMPT_NOT_FOUND = "This prompt doesn't exist in this project."
LABEL_NOT_FOUND = "The label {name} isn't set on this prompt."
VERSION_NOT_FOUND = "That version doesn't exist on this prompt."
CANDIDATE_VERSION = "An Improve candidate can't carry a label. Save it as a version first."
TOO_MANY = "This prompt already has {limit} labels. Remove one you no longer use first."
NOTHING_TO_ROLL_BACK = "The label {name} has never pointed anywhere else, so there is nothing to roll back to."
NOTHING_SERVED = (
    "No prompt called {name} with the label {label} was found in this project. "
    "Check the name and set the label on the Prompt screen."
)
NOTHING_SERVED_PLAIN = "No prompt called {name} was found in this project."
NO_SUCH_VERSION = "The prompt {name} has no version {version}."
BOTH = "Ask for a label or a version number, not both."


def etag_of(version_id: uuid.UUID) -> str:
    return f'"{version_id.hex}"'


class LabelService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._repo = LabelRepository(session)
        self._prompts = PromptRepository(session)
        self._settings = settings

    async def list(self, project_id: uuid.UUID, prompt_id: uuid.UUID) -> LabelsOut:
        prompt = await self._prompt(project_id, prompt_id)
        rows = await self._repo.labels(prompt.id)
        out = []
        for label, number in rows:
            pairs = await self._repo.move_pairs(prompt.id, label.name, self._settings.prompt_label_history_depth)
            out.append(
                PromptLabelOut(
                    name=label.name,
                    version_id=label.prompt_version_id,
                    version=number,
                    moved_at=label.moved_at,
                    can_roll_back=rollback_target(pairs, label.prompt_version_id) is not None,
                )
            )
        return LabelsOut(labels=out, accept_moves_label=prompt.accept_moves_label)

    async def assign(
        self,
        project_id: uuid.UUID,
        principal: Principal | None,
        prompt_id: uuid.UUID,
        name: str,
        version_id: uuid.UUID,
        reason: MoveReason = MoveReason.ASSIGN,
    ) -> PromptLabelOut:
        prompt = await self._prompt(project_id, prompt_id, lock=True)
        version = await self._version(prompt.id, version_id)
        existing = await self._repo.label(prompt.id, name, lock=True)
        if existing is not None and existing.prompt_version_id == version.id:
            return await self._out(prompt.id, existing, version.version)
        if existing is None and await self._repo.label_count(prompt.id) >= self._settings.prompt_labels_max:
            raise Conflict(TOO_MANY.format(limit=self._settings.prompt_labels_max))
        now = utcnow()
        before = existing.prompt_version_id if existing else None
        if existing is None:
            existing = PromptLabel(prompt_id=prompt.id, name=name, prompt_version_id=version.id, moved_at=now)
            await self._repo.add_label(existing)
        else:
            existing.prompt_version_id = version.id
            existing.moved_at = now
        await self._record(prompt.id, name, before, version.id, reason, principal)
        return await self._out(prompt.id, existing, version.version)

    async def remove(self, project_id: uuid.UUID, principal: Principal | None, prompt_id: uuid.UUID, name: str) -> None:
        prompt = await self._prompt(project_id, prompt_id, lock=True)
        label = await self._repo.label(prompt.id, name, lock=True)
        if label is None:
            raise NotFound(LABEL_NOT_FOUND.format(name=name))
        await self._repo.delete_label(label)
        await self._record(prompt.id, name, label.prompt_version_id, None, MoveReason.REMOVE, principal)

    async def rollback(
        self, project_id: uuid.UUID, principal: Principal | None, prompt_id: uuid.UUID, name: str
    ) -> PromptLabelOut:
        prompt = await self._prompt(project_id, prompt_id, lock=True)
        label = await self._repo.label(prompt.id, name, lock=True)
        if label is None:
            raise NotFound(LABEL_NOT_FOUND.format(name=name))
        pairs = await self._repo.move_pairs(prompt.id, name, self._settings.prompt_label_history_depth)
        target = rollback_target(pairs, label.prompt_version_id)
        if target is None:
            raise Conflict(NOTHING_TO_ROLL_BACK.format(name=name))
        return await self.assign(project_id, principal, prompt_id, name, target, MoveReason.ROLLBACK)

    async def history(
        self, project_id: uuid.UUID, prompt_id: uuid.UUID, name: str | None, page: PageParams
    ) -> Page[LabelMoveOut]:
        prompt = await self._prompt(project_id, prompt_id)
        rows = await self._repo.moves(prompt.id, name, page)
        items = [
            LabelMoveOut(
                id=move.id,
                label=move.label,
                reason=MoveReason(move.reason),
                from_version=before,
                to_version=after,
                moved_by=move.moved_by,
                moved_by_name=who,
                created_at=move.created_at,
            )
            for move, before, after, who in rows
        ]
        return to_page(items, page, lambda item: item.id)

    async def set_accept_label(self, project_id: uuid.UUID, prompt_id: uuid.UUID, name: str | None) -> LabelsOut:
        prompt = await self._prompt(project_id, prompt_id, lock=True)
        await self._repo.set_accept_label(prompt, name)
        return await self.list(project_id, prompt_id)

    async def move_on_accept(
        self, project_id: uuid.UUID, principal: Principal | None, prompt_id: uuid.UUID, version_id: uuid.UUID
    ) -> str | None:
        """Called after Accept saves a version. Moves the label the prompt names for this, if any, and says which."""
        prompt = await self._prompt(project_id, prompt_id)
        if prompt.accept_moves_label is None:
            return None
        await self.assign(project_id, principal, prompt_id, prompt.accept_moves_label, version_id, MoveReason.ACCEPT)
        return prompt.accept_moves_label

    async def fetch(
        self, project_id: uuid.UUID, name: str, label: str | None, version: int | None
    ) -> tuple[FetchedPrompt, str]:
        if label is not None and version is not None:
            raise ValidationFailed(BOTH)
        found = await self._repo.served_version(project_id, name, label, version)
        if found is None:
            if version is not None:
                raise NotFound(NO_SUCH_VERSION.format(name=name, version=version))
            raise NotFound(
                NOTHING_SERVED.format(name=name, label=label) if label else NOTHING_SERVED_PLAIN.format(name=name)
            )
        row, updated_at = found
        return _fetched(name, label, row, updated_at), etag_of(row.id)

    async def _out(self, prompt_id: uuid.UUID, label: PromptLabel, number: int) -> PromptLabelOut:
        pairs = await self._repo.move_pairs(prompt_id, label.name, self._settings.prompt_label_history_depth)
        return PromptLabelOut(
            name=label.name,
            version_id=label.prompt_version_id,
            version=number,
            moved_at=label.moved_at,
            can_roll_back=rollback_target(pairs, label.prompt_version_id) is not None,
        )

    async def _record(
        self,
        prompt_id: uuid.UUID,
        name: str,
        before: uuid.UUID | None,
        after: uuid.UUID | None,
        reason: MoveReason,
        principal: Principal | None,
    ) -> None:
        await self._repo.add_move(
            PromptLabelMove(
                prompt_id=prompt_id,
                label=name,
                from_version_id=before,
                to_version_id=after,
                reason=reason.value,
                moved_by=principal.user_id if principal else None,
            )
        )

    async def _prompt(self, project_id: uuid.UUID, prompt_id: uuid.UUID, lock: bool = False) -> Prompt:
        prompt = await self._prompts.prompt(project_id, prompt_id, lock=lock)
        if prompt is None:
            raise NotFound(PROMPT_NOT_FOUND)
        return prompt

    async def _version(self, prompt_id: uuid.UUID, version_id: uuid.UUID) -> PromptVersion:
        row = await self._prompts.version_of(prompt_id, version_id)
        if row is None:
            raise NotFound(VERSION_NOT_FOUND)
        if row.is_candidate:
            raise ValidationFailed(CANDIDATE_VERSION)
        return row


def _fetched(name: str, label: str | None, row: PromptVersion, updated_at: object) -> FetchedPrompt:
    return FetchedPrompt.model_validate(
        {
            "name": name,
            "label": label,
            "version": row.version,
            "version_id": row.id,
            "system_template": row.system_template,
            "user_template": row.user_template,
            "variables": row.variables,
            "default_params": row.default_params,
            "updated_at": updated_at,
        }
    )
