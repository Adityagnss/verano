"""
The security pack generation job: built-in attacks first (free, always the same), then, when a model was chosen,
extra attacks tailored to the app. Every case is a draft until a person approves it. Idempotent: it only works on a
pack that is still "generating" and starts by clearing that pack's cases. A model that fails or refuses only costs
its extra attacks: the built-in ones fill the gap and a note says so.
"""

import uuid
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import Container
from app.core.errors import AppError
from app.core.ids import uuid7
from app.core.leases import Heartbeat, deadline
from app.core.registry import load_plugins
from app.core.security import utcnow
from app.core.templates import render_system_prompt
from app.modules.gateway.dependencies import build_gateway
from app.modules.gateway.schemas import CallContext, CallPurpose, Message
from app.modules.gateway.service import GatewayService
from app.modules.prompts.domain import analyze
from app.modules.prompts.schemas import PromptShape
from app.modules.prompts.service import PromptService
from app.modules.registry.schemas import CallTarget
from app.modules.registry.service import RegistryService
from app.modules.security.domain import attack_inputs
from app.modules.security.models import SecurityPack
from app.modules.security.plugins import ATTACKS, AttackGenerator, Seed
from app.modules.security.repository import SecurityRepository

load_plugins("app.modules.security.plugins")
PROMPTS_DIR = Path(__file__).parent / "prompts"
MODEL_SHARE = 0.5
MODEL_FAILED = "The model could not write extra attacks for {title} ({why}), so built-in ones were used."


class AttackDraft(BaseModel):
    text: str = Field(min_length=1, max_length=4_000)
    safe_behaviour: str = Field(min_length=1, max_length=1_000)


class AttackDrafts(BaseModel):
    attacks: list[AttackDraft] = Field(min_length=1)


def split_counts(per_category: int, has_model: bool) -> tuple[int, int]:
    """(built-in, written by the model): with a model, half and half; without one, all built-in."""
    if not has_model:
        return per_category, 0
    built_in = max(1, round(per_category * (1 - MODEL_SHARE)))
    return built_in, per_category - built_in


class SecurityPipeline:
    def __init__(self, session: AsyncSession, container: Container) -> None:
        self._session = session
        self._container = container
        self._settings = container.settings
        self._repo = SecurityRepository(session)
        self._registry = RegistryService(session, container)
        self._gateway: GatewayService = build_gateway(container, self._registry)
        self._prompts = PromptService(session, self._registry, container.settings)

    async def generate(self, pack_id: uuid.UUID) -> None:
        pack = await self._repo.pack(pack_id)
        if pack is None or pack.status != "generating":
            return
        await self._repo.update_pack(pack.id, {"lease_expires_at": deadline(utcnow(), self._settings.lease_seconds)})
        await self._session.commit()

        async def beat() -> None:
            async with self._container.database.sessions() as own:
                await SecurityRepository(own).update_pack(
                    pack_id, {"lease_expires_at": deadline(utcnow(), self._settings.lease_seconds)}, "generating"
                )
                await own.commit()

        async with Heartbeat(beat, self._settings.lease_seconds / 3):
            await self._build(pack_id)

    async def fail(self, pack_id: uuid.UUID, message: str) -> None:
        await self._session.rollback()
        await self._repo.update_pack(pack_id, {"status": "failed", "message": message, "lease_expires_at": None})
        await self._session.commit()

    async def _build(self, pack_id: uuid.UUID) -> None:
        pack = await self._repo.pack(pack_id)
        assert pack is not None
        prompt = await self._prompts.get_version(pack.project_id, pack.prompt_version_id)
        info = analyze(prompt.system_template, prompt.user_template)
        system_only = info.shape is PromptShape.SYSTEM_ONLY
        target = None
        if pack.generator:
            target = await self._registry.call_target(
                pack.project_id, uuid.UUID(pack.generator["credential_id"]), pack.generator["model"]
            )
        await self._session.commit()
        await self._repo.delete_cases(pack.id)
        rows: list[dict[str, object]] = []
        notes: list[str] = []
        position = 0
        for name in pack.categories:
            family = ATTACKS[name]
            built_in, wanted = split_counts(pack.per_category, target is not None)
            seeds = family.seeds(built_in, pack.canary)
            written: list[Seed] = []
            if target is not None and wanted:
                try:
                    written = await self._ask(
                        family,
                        target,
                        pack,
                        prompt.system_template,
                        prompt.user_template,
                        seeds,
                        wanted,
                        info.required_inputs[0] if info.required_inputs else None,
                    )
                except AppError as error:
                    notes.append(MODEL_FAILED.format(title=family.title, why=error.message[:120]))
            missing = pack.per_category - len(seeds) - len(written)
            if missing > 0:  # the model wrote fewer than asked: more built-in attacks fill the gap
                seeds = family.seeds(built_in + missing, pack.canary)
            batch = [("built_in", s) for s in seeds] + [("model", s) for s in written]
            seen: set[str] = set()
            for source, seed in batch:
                key = " ".join(seed.text.lower().split())
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {
                        "id": uuid7(),
                        "pack_id": pack.id,
                        "category": name,
                        "attack": seed.text,
                        "inputs": attack_inputs(info.required_inputs, seed.text, system_only),
                        "safe_behaviour": seed.safe_behaviour,
                        "source": source,
                        "status": "draft",
                        "position": position,
                    }
                )
                position += 1
        await self._repo.insert_cases(rows)
        message = " ".join(notes) or "Read the attacks, edit or reject any you do not want, then approve the pack."
        await self._repo.update_pack(pack.id, {"status": "draft", "message": message, "lease_expires_at": None})
        await self._session.commit()

    async def _ask(
        self,
        family: AttackGenerator,
        target: CallTarget,
        pack: SecurityPack,
        system_template: str | None,
        user_template: str | None,
        examples: list[Seed],
        count: int,
        input_name: str | None,
    ) -> list[Seed]:
        text = render_system_prompt(
            PROMPTS_DIR,
            "attacks.jinja",
            count=count,
            ask=family.ask,
            input_name=input_name,
            system_template=(system_template or "")[:4_000] or None,
            user_template=(user_template or "")[:2_000] or None,
            examples=[e.text for e in examples],
        )
        context = CallContext(project_id=pack.project_id, labels={"step": "security_attacks", "family": family.id})
        drafts = await self._gateway.complete_json_target(
            target, [Message(role="user", content=text)], AttackDrafts, CallPurpose.GENERATION, context
        )
        return [Seed(d.text.strip(), d.safe_behaviour.strip()) for d in drafts.attacks[:count]]
