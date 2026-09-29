"""
Pure Prompt Studio logic: prompt shape, variables, rendering and the pre-run checks.

- `analyze` reads both templates' syntax trees once: which shape the prompt has, which
  `{{variables}}` it reads, and which inputs a test case must therefore provide (a
  system-only prompt also needs the "User message input"). A template that doesn't parse
  is reported with the template and line number.
- `render` turns one case's inputs into chat messages for any of the three shapes. All
  missing inputs are reported together; nothing is ever rendered as an empty string.
- `context_fits` estimates whether a rendered prompt plus the reply budget fits each
  model's context window; an unknown window is reported as unknown, not as fitting.
No I/O: the service supplies templates, inputs and model profiles.
"""

from dataclasses import dataclass
from typing import Any

from jinja2.exceptions import UndefinedError

from app.core.errors import ValidationFailed
from app.core.templates import TemplateSyntaxError, render_string, template_variables
from app.core.tokens import estimate_tokens
from app.modules.gateway.schemas import Message
from app.modules.prompts.schemas import ATTACHMENT_INPUT, USER_MESSAGE_INPUT, ContextFit, PromptShape
from app.modules.registry.schemas import ModelProfileOut

SHAPES: dict[tuple[bool, bool], PromptShape] = {
    (True, True): PromptShape.SYSTEM_AND_USER,
    (True, False): PromptShape.SYSTEM_ONLY,
    (False, True): PromptShape.USER_ONLY,
}
EXTRA_INPUTS: dict[PromptShape, tuple[str, ...]] = {PromptShape.SYSTEM_ONLY: (USER_MESSAGE_INPUT,)}


@dataclass(frozen=True)
class TemplateInfo:
    shape: PromptShape
    variables: list[str]
    required_inputs: list[str]


def shape_of(system_template: str | None, user_template: str | None) -> PromptShape:
    return SHAPES[(system_template is not None, user_template is not None)]


def _variables(label: str, template: str | None) -> set[str]:
    if template is None:
        return set()
    try:
        return template_variables(template)
    except TemplateSyntaxError as exc:
        message = f"The {label} prompt has a template error on line {exc.lineno}: {exc.message}"
        raise ValidationFailed(message, {"template": label, "line": exc.lineno}) from exc


def analyze(system_template: str | None, user_template: str | None) -> TemplateInfo:
    shape = shape_of(system_template, user_template)
    variables = sorted(_variables("system", system_template) | _variables("user", user_template))
    required = sorted({*variables, *EXTRA_INPUTS.get(shape, ())})
    return TemplateInfo(shape=shape, variables=variables, required_inputs=required)


def missing_inputs(required: list[str], available: list[str]) -> list[str]:
    return sorted(set(required) - set(available))


def _render(template: str, inputs: dict[str, Any]) -> str:
    try:
        return render_string(template, **inputs)
    except UndefinedError as exc:
        raise ValidationFailed(f"The prompt uses a value this case doesn't have: {exc.message}") from exc


def render(system_template: str | None, user_template: str | None, inputs: dict[str, Any]) -> list[Message]:
    info = analyze(system_template, user_template)
    attachment = inputs.get(ATTACHMENT_INPUT)
    if attachment is not None and info.shape is PromptShape.SYSTEM_ONLY:
        inputs = {USER_MESSAGE_INPUT: attachment, **inputs}
    missing = missing_inputs(info.required_inputs, list(inputs))
    if missing:
        raise ValidationFailed(f"This case is missing: {', '.join(missing)}.", {"missing_inputs": missing})
    values = {name: "" if value is None else value for name, value in inputs.items()}
    messages = [Message(role="system", content=_render(system_template, values))] if system_template else []
    user = _render(user_template, values) if user_template else str(values[USER_MESSAGE_INPUT])
    if attachment is not None and user_template and ATTACHMENT_INPUT not in info.variables:
        user = f"{user}\n\n{attachment}"
    return [*messages, Message(role="user", content=user)]


def context_fits(
    messages: list[Message], profiles: list[ModelProfileOut], max_tokens: int | None, chars_per_token: int
) -> list[ContextFit]:
    tokens = estimate_tokens((message.content for message in messages), max_tokens, chars_per_token)
    return [
        ContextFit(
            model_profile_id=profile.id,
            display_name=profile.display_name,
            context_window=profile.context_window,
            estimated_tokens=tokens,
            fits=None if profile.context_window is None else tokens <= profile.context_window,
        )
        for profile in profiles
    ]
