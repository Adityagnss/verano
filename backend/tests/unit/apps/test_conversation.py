"""Conversations with an app (ADR 0027): a scripted simulated user ends at the goal, at the turn limit or when
the app fails.
"""

import json
from collections.abc import Callable

import httpx

from app.core.config import Settings
from app.modules.apps.conversation import DONE, Ended, Simulator, converse
from app.modules.apps.mapping import ResponseMapping
from app.modules.apps.runner import AppRunner, AppSpec

SPEC = AppSpec(
    url="http://127.0.0.1/chat",
    method="POST",
    request_template='{"message": {{ message | tojson }}, "turn": {{ turn }}}',
    mapping=ResponseMapping("$.answer", None, "$.tool_calls", None),
    timeout_s=5.0,
    retries=0,
)
SETTINGS = Settings(_env_file=None, app_allowed_hosts=["127.0.0.1"])


def runner(handler: Callable[[httpx.Request], httpx.Response]) -> AppRunner:
    return AppRunner(SETTINGS, httpx.MockTransport(handler))


def scripted(*messages: str | None) -> tuple[Simulator, list[int]]:
    queue, seen = list(messages), []

    async def simulate(history: list[dict[str, str]]) -> str | None:
        seen.append(len(history))
        return queue.pop(0) if queue else None

    return simulate, seen


def echo(request: httpx.Request) -> httpx.Response:
    sent = json.loads(request.content)
    return httpx.Response(
        200, json={"answer": f"you said: {sent['message']}", "tool_calls": [{"name": "look", "arguments": {}}]}
    )


async def test_the_conversation_ends_when_the_simulated_user_says_the_goal_is_reached() -> None:
    simulate, seen = scripted("hello", "my order is A1001", DONE)
    found = await converse(runner(echo), SPEC, {}, {"goal": "find my order"}, simulate, max_turns=8)
    assert found.ended is Ended.GOAL_REACHED
    assert [turn["role"] for turn in found.history] == ["user", "assistant", "user", "assistant"]
    assert found.history[1]["content"] == "you said: hello"
    assert len(found.calls) == 2
    assert len(found.tool_calls) == 2
    assert seen == [0, 2, 4]  # the simulator saw the growing history each time


async def test_the_conversation_stops_at_the_turn_limit() -> None:
    simulate, _ = scripted("one", "two", "three", "four")
    found = await converse(runner(echo), SPEC, {}, {}, simulate, max_turns=2)
    assert found.ended is Ended.TURN_LIMIT
    assert len(found.calls) == 2


async def test_an_opening_message_is_used_without_asking_the_simulator() -> None:
    simulate, seen = scripted(DONE)
    found = await converse(runner(echo), SPEC, {"opening": "Hi there"}, {"opening": "Hi there"}, simulate, 8)
    assert found.history[0] == {"role": "user", "content": "Hi there"}
    assert seen == [2]


async def test_an_app_failure_ends_the_conversation_with_the_reason() -> None:
    simulate, _ = scripted("hello", "again")
    found = await converse(
        runner(lambda request: httpx.Response(500, text="boom")),
        SPEC,
        {},
        {},
        simulate,
        8,
    )
    assert found.ended is Ended.APP_ERROR
    assert "500" in (found.error or "")


def test_the_transcript_is_the_text_the_judges_read() -> None:
    from app.modules.apps.conversation import Conversation

    found = Conversation(history=[{"role": "user", "content": "hi"}], ended=Ended.GOAL_REACHED)
    assert json.loads(found.transcript()) == {"ended": "goal_reached", "turns": [{"role": "user", "content": "hi"}]}
