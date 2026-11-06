"""
Judge criteria written from the task, and the rubric self-check (ADR 0038).

A judge can write the criteria it will later score with, from the Task Spec and the prompt under test. Any rubric,
written by it or by a person, can be checked before it is used: free checks first (too few or too many criteria,
repeats, vague one-liners), then one judge call that reads the rubric critically for criteria that cannot be
answered from the case, that are vague, or that contradict each other. Issues are returned for a person to act
on; nothing is changed, scored or saved here.
"""

import uuid

from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import Container
from app.core.errors import AppError, NotFound, ValidationFailed
from app.modules.evaluation.judging import (
    GeneratedCriteria,
    RubricIssue,
    RubricReview,
    check_prompt,
    clean_criteria,
    local_issues,
    prompt_text,
    trusted_issues,
    write_prompt,
)
from app.modules.evaluation.schemas import JudgeChoice
from app.modules.gateway.dependencies import build_gateway
from app.modules.gateway.schemas import CallContext, CallPurpose, Message
from app.modules.gateway.service import GatewayService
from app.modules.generator.repository import TaskSpecRepository
from app.modules.generator.schemas import TaskSpec
from app.modules.prompts.repository import PromptRepository
from app.modules.registry.service import RegistryService

NO_SPEC = "This Task Spec doesn't exist in this project."
NO_PROMPT = "This prompt version doesn't exist in this project."
NOT_USABLE = "The judge did not answer in a form that could be used. Try again, or choose another judge model."
NOTHING_WRITTEN = "The judge wrote no usable criteria. Try again, or add a hint about what matters."
NEEDS_CRITERIA = "Give at least one criterion to check."
MAX_LISTED = 20


class CriteriaRequest(BaseModel):
    judge: JudgeChoice
    task_spec_id: uuid.UUID
    prompt_version_id: uuid.UUID | None = Field(
        default=None, description="Defaults to the prompt version the Task Spec was written for."
    )
    count: int | None = Field(default=None, ge=1, le=MAX_LISTED, description="How many criteria; the server default.")
    focus: str | None = Field(default=None, max_length=1000, description="A hint about what matters most.")
    check: bool = Field(default=True, description="Also run the rubric self-check on what was written.")


class RubricCheckRequest(BaseModel):
    criteria: list[str] = Field(min_length=1, max_length=MAX_LISTED)
    judge: JudgeChoice | None = Field(default=None, description="Leave out to run only the free checks.")
    task_spec_id: uuid.UUID | None = None
    prompt_version_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _something_to_check(self) -> "RubricCheckRequest":
        if not any(text.strip() for text in self.criteria):
            raise ValueError(NEEDS_CRITERIA)
        return self


class RubricCheckOut(BaseModel):
    ok: bool
    issues: list[RubricIssue]
    judged: bool  # whether a judge read the rubric (false: only the free checks ran)
    summary: str


class CriteriaOut(BaseModel):
    criteria: list[str]
    review: RubricCheckOut | None
    evaluator_config: dict[str, object]  # a judged check made of these criteria, ready to add to the checks


def summary_of(issues: list[RubricIssue], judged: bool) -> str:
    if not issues:
        return (
            "No problems found: every criterion looks answerable, specific and consistent."
            if judged
            else "No problems found by the free checks. Run the judge check too for a closer read."
        )
    many = len(issues)
    return f"{many} possible problem{'s' if many != 1 else ''} found. Fix or remove them before relying on this rubric."


class RubricService:
    def __init__(self, session: AsyncSession, container: Container) -> None:
        self._settings = container.settings
        self._registry = RegistryService(session, container)
        self._gateway: GatewayService = build_gateway(container, self._registry)
        self._specs = TaskSpecRepository(session)
        self._prompts = PromptRepository(session)

    async def generate(self, project_id: uuid.UUID, body: CriteriaRequest) -> CriteriaOut:
        """The judge writes criteria from the task and the prompt; the self-check then reads them."""
        spec, prompt_version_id = await self._spec(project_id, body.task_spec_id)
        prompt = await self._prompt(project_id, body.prompt_version_id or prompt_version_id)
        settings = self._settings
        count = body.count or round((settings.rubric_criteria_min + settings.rubric_criteria_max) / 2)
        asked = write_prompt(spec.goal, prompt, spec.constraints, spec.risk_areas, count, body.focus)
        written = await self._ask(project_id, body.judge, asked, GeneratedCriteria, "rubric_write")
        criteria = clean_criteria(written.criteria, settings.rubric_max_criterion_chars)[: max(count, 1)]
        if not criteria:
            raise ValidationFailed(NOTHING_WRITTEN)
        review = await self._review(project_id, criteria, body.judge, spec.goal, prompt) if body.check else None
        joined = " ".join(f"({n}) {text}" for n, text in enumerate(criteria, start=1))
        config: dict[str, object] = {
            "kind": "deepeval",
            "metric": "g_eval",
            "criteria": f"A good answer meets every one of these criteria: {joined}",
        }
        return CriteriaOut(criteria=criteria, review=review, evaluator_config=config)

    async def check(self, project_id: uuid.UUID, body: RubricCheckRequest) -> RubricCheckOut:
        """The rubric self-check: free checks, and a judge's critical read when a judge is given."""
        goal, prompt = None, None
        if body.task_spec_id:
            spec, version_id = await self._spec(project_id, body.task_spec_id)
            goal = spec.goal
            prompt = await self._prompt(project_id, body.prompt_version_id or version_id)
        elif body.prompt_version_id:
            prompt = await self._prompt(project_id, body.prompt_version_id)
        criteria = clean_criteria(body.criteria, self._settings.rubric_max_criterion_chars * 4)
        return await self._review(project_id, criteria, body.judge, goal, prompt)

    async def _review(
        self,
        project_id: uuid.UUID,
        criteria: list[str],
        judge: JudgeChoice | None,
        goal: str | None,
        prompt: str | None,
    ) -> RubricCheckOut:
        settings = self._settings
        issues = local_issues(
            criteria, settings.rubric_criteria_min, settings.rubric_criteria_max, settings.rubric_max_criterion_chars
        )
        if judge is not None:
            reply = await self._ask(
                project_id, judge, check_prompt(criteria, goal, prompt), RubricReview, "rubric_check"
            )
            issues = [*issues, *trusted_issues(reply, len(criteria))]
        judged = judge is not None
        return RubricCheckOut(ok=not issues, issues=issues, judged=judged, summary=summary_of(issues, judged))

    async def _ask[M: BaseModel](
        self, project_id: uuid.UUID, judge: JudgeChoice, prompt: str, schema: type[M], what: str
    ) -> M:
        target = await self._registry.call_target(project_id, judge.credential_id, judge.model)
        context = CallContext(project_id=project_id, labels={"judging": what})
        try:
            return await self._gateway.complete_json_target(
                target, [Message(role="user", content=prompt)], schema, CallPurpose.JUDGE, context
            )
        except AppError as exc:
            if exc.code == "structured_output_error":
                raise ValidationFailed(NOT_USABLE) from exc
            raise

    async def _spec(self, project_id: uuid.UUID, spec_id: uuid.UUID) -> tuple[TaskSpec, uuid.UUID]:
        record = await self._specs.get(project_id, spec_id)
        if record is None:
            raise NotFound(NO_SPEC)
        return TaskSpec.model_validate(record.spec), record.prompt_version_id

    async def _prompt(self, project_id: uuid.UUID, version_id: uuid.UUID) -> str | None:
        version = await self._prompts.version(project_id, version_id)
        if version is None:
            raise NotFound(NO_PROMPT)
        return prompt_text(version.system_template, version.user_template, self._settings.judge_prompt_max_chars)
