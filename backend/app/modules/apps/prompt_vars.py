"""
How an app receives the prompt Improve is testing (ADR 0036). Pure code.

An app is called with a request template. If that template uses `{{ system_prompt }}` or `{{ user_prompt }}`, Verano
fills them with the rendered prompt of the version being tested, so a candidate prompt really reaches the app and
Improve can work on it. A template without them never sees the prompt: Improve would be changing something the app
ignores, so it says so instead of pretending. A test case's own input with the same name always wins.
"""

from typing import Any

from jinja2 import TemplateSyntaxError

from app.core.errors import ValidationFailed
from app.core.templates import template_variables
from app.modules.prompts.domain import render

SYSTEM_VARIABLE = "system_prompt"
USER_VARIABLE = "user_prompt"
PROMPT_VARIABLES = frozenset({SYSTEM_VARIABLE, USER_VARIABLE})
NOT_ACCEPTED = (
    "The app “{name}” does not take the prompt: its request template uses neither {{{{ system_prompt }}}} nor "
    "{{{{ user_prompt }}}}, so a better prompt written by Improve would never reach it. Add one of them to the "
    "request template (where your app expects its instructions), or use the failure report instead."
)


def accepts_prompt(request_template: str) -> bool:
    try:
        return bool(template_variables(request_template) & PROMPT_VARIABLES)
    except TemplateSyntaxError:
        return False


def with_prompt(
    request_template: str, inputs: dict[str, Any], system_template: str | None, user_template: str | None
) -> dict[str, Any]:
    """The case's inputs plus the rendered prompt, only for the variables the request template actually uses."""
    try:
        wanted = template_variables(request_template) & PROMPT_VARIABLES
    except TemplateSyntaxError:
        return inputs
    if not wanted:
        return inputs
    try:
        messages = render(system_template, user_template, inputs)
    except ValidationFailed:
        return inputs
    system = next((m.content for m in messages if m.role == "system"), "")
    user = next((m.content for m in messages if m.role == "user"), "")
    found = {SYSTEM_VARIABLE: system, USER_VARIABLE: user}
    return {**{name: found[name] for name in wanted}, **inputs}
