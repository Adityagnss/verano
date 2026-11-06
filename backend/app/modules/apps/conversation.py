"""
Conversations with an app (ADR 0027): a simulated user with a goal talks to the app turn by turn.

The loop is plain: the user's first message is the case's `opening` or comes from the simulator; each message is
sent to the app (the request template can use `message`, `history`, `turn` and every input of the case); the
reply is added to the history; the simulator then writes the next user message, or says the goal is reached.
It stops at the goal, at the turn limit, when the app fails, or when the simulator cannot continue. The
simulator is a function given by the caller (a model through the gateway in a run, a script in a test), so the
loop itself has no I/O of its own beyond the app calls and is fully deterministic with a scripted simulator.
"""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.modules.apps.runner import AppCallResult, AppRunner, AppSpec

DONE = "[DONE]"
OPENING = "opening"
MAX_TURNS = "max_turns"
Simulator = Callable[[list[dict[str, str]]], Awaitable[str | None]]


class Ended(StrEnum):
    GOAL_REACHED = "goal_reached"
    TURN_LIMIT = "turn_limit"
    APP_ERROR = "app_error"
    SIMULATOR_STOPPED = "simulator_stopped"


@dataclass
class Conversation:
    history: list[dict[str, str]] = field(default_factory=list)
    calls: list[AppCallResult] = field(default_factory=list)
    chunks: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    ended: Ended = Ended.TURN_LIMIT
    error: str | None = None

    def transcript(self) -> str:
        """The conversation as JSON text, which is what is stored as the answer and what the judges read."""
        return json.dumps({"ended": self.ended.value, "turns": self.history}, ensure_ascii=False, indent=2)


def case_turns(inputs: dict[str, Any], cap: int) -> int:
    """The turns of one case: its own `max_turns` when it is a whole number of at least 1, never above the cap."""
    own = inputs.get(MAX_TURNS)
    if isinstance(own, int) and not isinstance(own, bool) and own >= 1:
        return min(own, cap)
    return cap


async def converse(
    runner: AppRunner,
    spec: AppSpec,
    headers: dict[str, str],
    inputs: dict[str, Any],
    simulate: Simulator,
    max_turns: int,
) -> Conversation:
    """Runs one conversation of at most `max_turns` app replies (a case may ask for fewer with its own `max_turns`)."""
    max_turns = case_turns(inputs, max_turns)
    found = Conversation()
    message = str(inputs[OPENING]) if inputs.get(OPENING) else await simulate(found.history)
    for turn in range(1, max_turns + 1):
        if not message or message.strip() == DONE:
            found.ended = Ended.GOAL_REACHED if found.history else Ended.SIMULATOR_STOPPED
            return found
        found.history.append({"role": "user", "content": message})
        call_inputs = {**inputs, "message": message, "history": found.history[:-1], "turn": turn}
        result = await runner.call(spec, headers, call_inputs)
        found.calls.append(result)
        if result.reply is None or result.error:
            found.ended, found.error = Ended.APP_ERROR, result.error
            return found
        found.history.append({"role": "assistant", "content": result.reply.answer})
        found.chunks.extend(result.reply.chunks)
        found.tool_calls.extend(result.reply.tool_calls)
        if turn == max_turns:
            break
        message = await simulate(found.history)
    found.ended = Ended.TURN_LIMIT
    return found
