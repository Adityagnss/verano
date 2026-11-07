"""
Mock model behaviors for tests whose answers must depend on the prompt (the multi-round Improve tests): the model
answers a ticket correctly for a share of tickets that grows with the instructions the system prompt contains, so a
better prompt really scores better and a round can be proven (or not) without any real model. Registered once, when
conftest imports this file; `fixtures/mock_models.yaml` names them.
"""

import hashlib
from collections.abc import Callable

from app.modules.gateway.plugins.mock_provider import BEHAVIORS, MockLLM, MockRequest

QUARTERS = {"exactly one of": 2, "Examples:": 1, "Ignore any instructions": 1}
ROUND_TWO = "ROUND-TWO"


def _sensitive(round_two_quarters: int) -> Callable[[MockLLM, MockRequest], str]:
    def behavior(llm: MockLLM, request: MockRequest) -> str:
        system = next((str(m["content"]) for m in request.messages if m["role"] == "system"), "")
        quarters = max([share for marker, share in QUARTERS.items() if marker in system], default=0)
        if ROUND_TWO in system:
            quarters = max(quarters, round_two_quarters)
        ticket = request.last_user.strip()
        known = llm.answers()
        bucket = int(hashlib.md5(ticket.encode()).hexdigest(), 16) % 4
        return known[ticket] if ticket in known and bucket < quarters else "unknown"

    return behavior


BEHAVIORS.add("prompt_sensitive", _sensitive(4))
BEHAVIORS.add("prompt_sensitive_flat", _sensitive(2))
