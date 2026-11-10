"""The prompt drafter's template and its output shape; the model call itself is exercised against the real provider."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.templates import render_system_prompt
from app.modules.generator.schemas import PromptDraft
from app.modules.generator.service import PROMPTS_DIR


def test_template_carries_goal_and_documents() -> None:
    text = render_system_prompt(
        PROMPTS_DIR, "prompt_draft.jinja", goal="Answer refund questions", documents=["Refunds take 5 days."]
    )
    assert "PROMPT_DRAFT_REQUEST" in text and "Answer refund questions" in text and "Refunds take 5 days." in text
    assert "{{ question }}" in text


def test_template_without_goal_says_so() -> None:
    text = render_system_prompt(PROMPTS_DIR, "prompt_draft.jinja", goal=None, documents=["x"])
    assert "(not given)" in text


def test_draft_needs_both_templates() -> None:
    with pytest.raises(ValidationError):
        PromptDraft(system_template="", user_template="{{ q }}")
    assert Path(PROMPTS_DIR / "prompt_draft.jinja").exists()
