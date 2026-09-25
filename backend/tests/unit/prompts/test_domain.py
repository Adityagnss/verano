"""Unit tests for prompt shapes, variables, rendering and context-window checks."""

import uuid
from decimal import Decimal

import pytest

from app.core.errors import ValidationFailed
from app.modules.gateway.schemas import Message
from app.modules.prompts.domain import analyze, context_fits, render
from app.modules.prompts.schemas import USER_MESSAGE_INPUT, PromptShape
from app.modules.registry.schemas import ModelProfileOut, PriceSource

pytestmark = [pytest.mark.unit, pytest.mark.prompts]

SYSTEM = "You triage {{ product }} support tickets. Answer with one label."
USER = "Ticket from {{ customer.name }}:\n{{ ticket }}"


@pytest.mark.parametrize(
    ("system", "user", "shape", "required"),
    [
        (SYSTEM, USER, PromptShape.SYSTEM_AND_USER, ["customer", "product", "ticket"]),
        (SYSTEM, None, PromptShape.SYSTEM_ONLY, ["product", USER_MESSAGE_INPUT]),
        (None, USER, PromptShape.USER_ONLY, ["customer", "ticket"]),
    ],
)
def test_each_shape_declares_exactly_the_inputs_a_case_must_provide(
    system: str | None, user: str | None, shape: PromptShape, required: list[str]
) -> None:
    info = analyze(system, user)
    assert (info.shape, info.required_inputs) == (shape, required)


def test_the_three_shapes_render_to_the_right_messages() -> None:
    inputs = {
        "product": "Verano",
        "customer": {"name": "Ada"},
        "ticket": "I was charged twice",
        USER_MESSAGE_INPUT: "hi",
    }
    assert render(SYSTEM, USER, inputs) == [
        Message(role="system", content="You triage Verano support tickets. Answer with one label."),
        Message(role="user", content="Ticket from Ada:\nI was charged twice"),
    ]
    assert render(SYSTEM, None, inputs)[1] == Message(role="user", content="hi")
    assert [m.role for m in render(None, USER, inputs)] == ["user"]


def test_rendering_reports_every_missing_input_at_once_and_never_renders_blanks() -> None:
    with pytest.raises(ValidationFailed) as error:
        render(SYSTEM, USER, {"ticket": "hello"})
    assert error.value.details["missing_inputs"] == ["customer", "product"]


def test_a_template_that_does_not_parse_is_reported_with_its_line() -> None:
    with pytest.raises(ValidationFailed) as error:
        analyze("fine", "line one\n{{ ticket ")
    assert error.value.details == {"template": "user", "line": 2}


def profile(context_window: int | None) -> ModelProfileOut:
    return ModelProfileOut(
        id=uuid.uuid4(),
        credential_id=uuid.uuid4(),
        provider="mock",
        model_name="m",
        display_name="M",
        litellm_model="mock/m",
        context_window=context_window,
        max_output_tokens=None,
        parameters={},
        supports_json_mode=False,
        supports_system_prompt=True,
        input_price_per_mtok=Decimal(1),
        output_price_per_mtok=Decimal(1),
        price_source=PriceSource.OVERRIDE,
        price_known=True,
        is_selected=True,
    )


def test_context_fit_counts_the_reply_budget_and_treats_unknown_windows_as_unknown() -> None:
    messages = [Message(role="user", content="x" * 400)]
    fits = context_fits(messages, [profile(200), profile(50), profile(None)], max_tokens=50, chars_per_token=4)
    assert [(fit.estimated_tokens, fit.fits) for fit in fits] == [(151, True), (151, False), (151, None)]
