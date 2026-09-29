"""The Improve step's candidate request carries the measured prompt-technique notes."""

from app.core.templates import render_system_prompt
from app.modules.assistant.pipeline import PROMPTS_DIR


def test_the_candidate_request_includes_the_technique_notes_and_keeps_its_marker() -> None:
    text = render_system_prompt(
        PROMPTS_DIR,
        "candidates.jinja",
        spec={},
        system_template="Classify.",
        user_template=None,
        shape="system_only",
        groups=[],
        examples=[],
    )
    assert "CANDIDATES_REQUEST" in text
    assert "Measure, don't assume" in text
    assert "Personas" in text
