"""
Generating conversation cases for an app in conversation mode (ADR 0039).

One model call (a few at most, to top up) writes personas, goals, opening messages and stopping conditions from the
prompt and the Task Spec. They are stored as draft cases of the project's draft dataset version, so they are reviewed
and approved like any generated case, and they run on the conversation simulator (ADR 0027): `persona`, `goal`,
`scenario` and `stop_when` steer the simulated user, `opening` is the first message, and `max_turns` (never above the
`conversation_max_turns` setting) caps that conversation. The stopping condition is also the case's rubric, which is
what the judges read to decide whether the goal was reached. Pure helpers first, then the service.
"""

import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import Container
from app.core.errors import NotFound, ValidationFailed
from app.core.templates import render_system_prompt
from app.modules.apps.case_schemas import (
    ConversationCasesOut,
    ConversationCasesRequest,
    GeneratedConversationBatch,
    GeneratedConversationCase,
)
from app.modules.apps.repository import AppRepository
from app.modules.apps.schemas import AppMode
from app.modules.datasets.domain import is_blank
from app.modules.datasets.schemas import ItemSource, ReviewStatus
from app.modules.datasets.service import DatasetService
from app.modules.gateway.dependencies import build_gateway
from app.modules.gateway.schemas import CallContext, CallPurpose, Message
from app.modules.generator.domain import suggest_generator
from app.modules.generator.repository import TaskSpecRepository
from app.modules.generator.schemas import GeneratorModel
from app.modules.projects.schemas import ProjectOut
from app.modules.prompts.service import PromptService
from app.modules.registry.service import RegistryService

PROMPTS = Path(__file__).parent / "prompts"
APP_PROVIDER = "app"
NOT_FOUND = "This app doesn't exist in this project."
NOT_A_CONVERSATION = (
    "This app answers one message at a time. Switch it to conversation mode to generate conversation cases for it."
)
NO_PROMPT = "Save a prompt (step 2) first: the conversation cases are written from it."
NO_GENERATOR = "Choose a model to write the cases: no model of this project can be used for it."
SAVED = "Wrote {added} conversation case(s) as drafts. Review and approve them like any other test case."
NOTHING = "The model did not write any usable new conversation case. Try again, or describe what to focus on."
DUPLICATES = " {count} were left out because they repeat a case you already have."


def _same(text: str) -> str:
    return " ".join(text.lower().split())


def accept_cases(
    written: list[GeneratedConversationCase], covered: set[str], want: int, turn_cap: int
) -> tuple[list[dict[str, Any]], int, int]:
    """The new cases as dataset rows (at most `want`), and how many were left out as repeats or blank. A case repeats
    when its goal or its opening message matches one already kept (the project's, or an earlier one of this batch)."""
    rows: list[dict[str, Any]] = []
    seen = set(covered)
    repeats = blank = 0
    for case in written:
        if any(is_blank(value) for value in (case.persona, case.goal, case.opening, case.stop_when)):
            blank += 1
            continue
        keys = {_same(case.goal), _same(case.opening)}
        if keys & seen:
            repeats += 1
            continue
        if len(rows) == want:
            continue
        seen |= keys
        rows.append(case_row(case, turn_cap))
    return rows, repeats, blank


def case_row(case: GeneratedConversationCase, turn_cap: int) -> dict[str, Any]:
    """A draft dataset item for a conversation case; its turns are capped by the setting."""
    inputs: dict[str, Any] = {
        "persona": case.persona.strip(),
        "goal": case.goal.strip(),
        "opening": case.opening.strip(),
        "stop_when": case.stop_when.strip(),
    }
    if case.scenario and case.scenario.strip():
        inputs["scenario"] = case.scenario.strip()
    if case.max_turns is not None:
        inputs["max_turns"] = min(case.max_turns, turn_cap)
    return {
        "inputs": inputs,
        "expected_output": None,
        "rubric": [case.stop_when.strip()],
        "category": case.category.value,
        "tags": ["conversation"],
        "source": ItemSource.GENERATED,
        "review_status": ReviewStatus.DRAFT,
        "context": [],
        "extra": {"kind": "conversation"},
    }


def covered_keys(inputs: list[dict[str, Any]]) -> set[str]:
    """Goals and opening messages the dataset already has, to avoid writing them again."""
    return {_same(str(value)) for item in inputs for key in ("goal", "opening") if (value := item.get(key))}


class ConversationCaseService:
    def __init__(self, session: AsyncSession, container: Container) -> None:
        self._session = session
        self._settings = container.settings
        self._apps = AppRepository(session)
        self._registry = RegistryService(session, container)
        self._prompts = PromptService(session, self._registry, container.settings)
        self._datasets = DatasetService(session, container.settings)
        self._specs = TaskSpecRepository(session)
        self._gateway = build_gateway(container, self._registry)

    async def generate(
        self, project: ProjectOut, app_id: uuid.UUID, body: ConversationCasesRequest
    ) -> ConversationCasesOut:
        target = await self._apps.target(project.id, app_id)
        if target is None:
            raise NotFound(NOT_FOUND)
        if AppMode(target.mode) is not AppMode.CONVERSATION:
            raise ValidationFailed(NOT_A_CONVERSATION)
        want = min(body.count or self._settings.conversation_cases_default, self._settings.conversation_cases_max)
        prompt_id = body.prompt_version_id or await self._prompts.latest_version_id(project.id)
        if prompt_id is None:
            raise ValidationFailed(NO_PROMPT)
        prompt = await self._prompts.get_version(project.id, prompt_id)
        specs = await self._specs.confirmed_for_version(project.id, prompt.id)
        spec = specs[0].spec if specs else None
        model = body.generator or await self._suggested(project)
        draft = await self._datasets.ensure_draft(project.id)
        await self._datasets.draft_for_edit(project.id, draft.id)
        covered = covered_keys([item.inputs for item in await self._datasets.items(draft.id)])
        turn_cap = self._settings.conversation_max_turns
        added = repeats = blank = 0
        for _ in range(1 + self._settings.generator_top_up_rounds):
            missing = want - added
            if missing <= 0:
                break
            request = render_system_prompt(
                PROMPTS,
                "conversation_cases.jinja",
                count=missing,
                focus=body.focus,
                max_turns=turn_cap,
                app_name=target.name,
                spec=spec,
                system_template=prompt.system_template,
                user_template=prompt.user_template,
                covered=sorted(covered)[:50],
            )
            batch = await self._gateway.complete_json(
                model.model,
                [Message(role="user", content=request)],
                GeneratedConversationBatch,
                model.credential_id,
                CallPurpose.GENERATION,
                CallContext(project_id=project.id, labels={"step": "conversation_cases", "app": str(app_id)}),
            )
            rows, again, empty = accept_cases(batch.cases, covered, missing, turn_cap)
            repeats, blank = repeats + again, blank + empty
            if rows:
                await self._datasets.add_items(draft.id, rows)
                await self._session.commit()
                covered |= covered_keys([row["inputs"] for row in rows])
                added += len(rows)
        message = SAVED.format(added=added) if added else NOTHING
        if repeats:
            message += DUPLICATES.format(count=repeats)
        return ConversationCasesOut(
            dataset_version_id=draft.id,
            added=added,
            dropped_duplicates=repeats,
            dropped_invalid=blank,
            generator_model=model.model,
            message=message,
        )

    async def _suggested(self, project: ProjectOut) -> GeneratorModel:
        profiles = [p for p in await self._registry.profiles(project.id) if p.provider != APP_PROVIDER]
        chosen = suggest_generator(profiles)
        if chosen is None:
            raise ValidationFailed(NO_GENERATOR)
        return GeneratorModel(credential_id=chosen.credential_id, model=chosen.model_name)
