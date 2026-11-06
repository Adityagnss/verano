"""
The executor's way to call apps (ADR 0024): prepares each app target of a chunk once, then turns one test case
into the values the run row stores and the calls to record.

An answer that comes from an app is stored like any other: its text (cut at the stored-answer limit and flagged),
the retrieved chunks and tool calls the app reported, its latency and, only when the app reports it, its cost
("reported by your app"). Tokens are never invented. A conversation's answer is its transcript. A call that
fails is a failed row with the reason, never a pass.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.container import Container
from app.core.text import bound
from app.modules.apps.conversation import Simulator, converse
from app.modules.apps.models import AppTarget
from app.modules.apps.repository import AppRepository
from app.modules.apps.runner import AppCallResult, AppRunner, AppSpec
from app.modules.apps.schemas import AppMode
from app.modules.apps.service import AppService, spec_of
from app.modules.engine.schemas import RunStatus

APP_ERROR = "app_error"
APP_CONVERSATION_FAILED = "The conversation stopped because the app failed: {why}"


@dataclass(frozen=True)
class PreparedApp:
    target_id: uuid.UUID
    name: str
    spec: AppSpec
    headers: dict[str, str]
    concurrency: int
    mode: AppMode


@dataclass
class AppOutcome:
    values: dict[str, Any]
    calls: list[dict[str, Any]]


def call_record(result: AppCallResult, turn: int) -> dict[str, Any]:
    return {
        "turn": turn,
        "request_body": result.request_body,
        "status_code": result.status_code,
        "response_body": result.response_body,
        "truncated": result.truncated,
        "latency_ms": result.latency_ms,
        "error": result.error,
    }


class AppCaller:
    def __init__(self, session: AsyncSession, container: Container, runner: AppRunner | None = None) -> None:
        self._repo = AppRepository(session)
        self._settings: Settings = container.settings
        self._service = AppService(session, container)
        self._runner = runner or AppRunner(container.settings)

    async def prepare(self, credential_ids: set[uuid.UUID]) -> dict[uuid.UUID, PreparedApp]:
        found = {}
        for credential_id in credential_ids:
            target = await self._repo.target_by_credential(credential_id)
            if target is not None:
                found[credential_id] = await self._prepared(target)
        return found

    async def _prepared(self, target: AppTarget) -> PreparedApp:
        return PreparedApp(
            target_id=target.id,
            name=target.name,
            spec=spec_of(target),
            headers=await self._service.headers(target),
            concurrency=target.concurrency,
            mode=AppMode(target.mode),
        )

    async def run(self, app: PreparedApp, inputs: dict[str, Any], simulate: Simulator | None) -> AppOutcome:
        if app.mode is AppMode.CONVERSATION and simulate is not None:
            return await self._conversation(app, inputs, simulate)
        result = await self._runner.call(app.spec, app.headers, inputs)
        return AppOutcome(self._single_values(result), [call_record(result, 0)])

    def _single_values(self, result: AppCallResult) -> dict[str, Any]:
        base: dict[str, Any] = {
            "rendered_user_prompt": result.request_body[: self._settings.stored_answer_max_chars],
            "latency_ms": result.latency_ms,
            "attempts": 1,
        }
        reply = result.reply
        if reply is None or result.error:
            return base | {"status": RunStatus.FAILED, "error_type": APP_ERROR, "error_message": result.error}
        answer, cut = bound(reply.answer, self._settings.stored_answer_max_chars)
        return base | {
            "status": RunStatus.SUCCEEDED,
            "raw_output": answer,
            "output_truncated": cut or result.truncated,
            "retrieved_chunks": reply.chunks or None,
            "tool_calls": reply.tool_calls or None,
            "cost": None if reply.cost is None else Decimal(str(reply.cost)),
        }

    async def _conversation(self, app: PreparedApp, inputs: dict[str, Any], simulate: Simulator) -> AppOutcome:
        found = await converse(
            self._runner, app.spec, app.headers, inputs, simulate, self._settings.conversation_max_turns
        )
        calls = [call_record(c, index + 1) for index, c in enumerate(found.calls)]
        latency = sum(c.latency_ms or 0 for c in found.calls)
        if found.error and not found.history:
            return AppOutcome(
                {
                    "status": RunStatus.FAILED,
                    "error_type": APP_ERROR,
                    "error_message": APP_CONVERSATION_FAILED.format(why=found.error),
                    "latency_ms": latency,
                    "attempts": 1,
                },
                calls,
            )
        text, cut = bound(found.transcript(), self._settings.stored_answer_max_chars)
        return AppOutcome(
            {
                "status": RunStatus.SUCCEEDED,
                "raw_output": text,
                "output_truncated": cut,
                "retrieved_chunks": found.chunks or None,
                "tool_calls": found.tool_calls or None,
                "latency_ms": latency,
                "attempts": len(found.calls) or 1,
            },
            calls,
        )
