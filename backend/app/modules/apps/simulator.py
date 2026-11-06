"""
The simulated user of a conversation (ADR 0027): one model, called through the gateway, that plays a person with a
goal. Its calls are recorded like any other model call (labelled as the simulator) and their cost is added to the
answer's cost, so the budget cap counts them. The model is the judge model of the experiment.
"""

from decimal import Decimal
from pathlib import Path
from typing import Any

from app.core.templates import render_system_prompt
from app.modules.apps.conversation import DONE, Simulator
from app.modules.gateway.schemas import CallContext, CallPurpose, Message
from app.modules.gateway.service import GatewayService
from app.modules.registry.schemas import CallTarget

PROMPTS = Path(__file__).parent / "prompts"
NO_GOAL = "Get a helpful answer."
HISTORY_LINE = "{role}: {content}"
FIRST_TURN = "The conversation has not started. Write the person's first message."
NEXT_TURN = "The conversation so far:\n{history}\n\nWrite the person's next message, or {done}."


class SimulatedUser:
    def __init__(
        self, gateway: GatewayService, target: CallTarget, context: CallContext, inputs: dict[str, Any]
    ) -> None:
        self._gateway, self._target, self._context = gateway, target, context
        self._inputs = inputs
        self.cost = Decimal(0)

    def as_simulator(self) -> Simulator:
        return self._next

    async def _next(self, history: list[dict[str, str]]) -> str | None:
        system = render_system_prompt(
            PROMPTS,
            "simulator.jinja",
            persona=self._inputs.get("persona"),
            goal=self._inputs.get("goal") or NO_GOAL,
            scenario=self._inputs.get("scenario"),
            done=DONE,
        )
        shown = "\n".join(HISTORY_LINE.format(role=turn["role"], content=turn["content"]) for turn in history)
        prompt = NEXT_TURN.format(history=shown, done=DONE) if history else FIRST_TURN
        result = await self._gateway.complete_target(
            self._target,
            [Message(role="system", content=system), Message(role="user", content=prompt)],
            {},
            CallPurpose.JUDGE,
            self._context.model_copy(update={"labels": {**self._context.labels, "role": "simulator"}}),
        )
        self.cost += result.cost or Decimal(0)
        text = result.text.strip()
        return text or None
