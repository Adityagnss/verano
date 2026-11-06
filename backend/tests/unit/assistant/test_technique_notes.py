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
        count=1,
        angle="",
        groups=[],
        examples=[],
        focus="quality",
        history=[],
    )
    assert "CANDIDATES_REQUEST" in text
    assert "The one habit: measure first" in text
    assert "Expert personas" in text


# Umbrella headings of the notes whose content the guide spreads over its own sections.
SPREAD_OVER_THE_GUIDE = {"Measure these (they depend on the model and the task)", "How the main techniques work"}


def test_the_prompt_guide_keeps_every_section_of_the_notes_improve_reads() -> None:
    def headings(name: str) -> set[str]:
        text = (PROMPTS_DIR / name).read_text(encoding="utf-8")
        return {line.lstrip("#").strip() for line in text.splitlines() if line.startswith(("## ", "### "))}

    missing = headings("technique_notes.md") - headings("prompt_guide.md") - SPREAD_OVER_THE_GUIDE
    assert not missing, f"the Prompt guide dropped sections Improve relies on: {missing}"
