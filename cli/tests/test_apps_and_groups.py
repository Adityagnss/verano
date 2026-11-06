"""verano app: inputs are read as name=value; prompts with the same group share one project."""

from pathlib import Path

import pytest

from verano.apps import parse_inputs
from verano.errors import CliError
from verano.loader import SEPARATOR, load

GROUPED = """\
version: 1
project: support-bot
prompts:
  - name: classify
    group: tickets
    system: Classify the ticket.
    task: {type: classification, goal: Label tickets, allowed_outputs: [billing, other]}
    models: [gpt-4o-mini]
  - name: summarise
    group: tickets
    system: Summarise the ticket.
    task: {type: summarization, goal: Summarise tickets}
    models: [gpt-4o-mini]
  - name: alone
    system: Say hello.
    task: {type: generation, goal: Greet}
    models: [gpt-4o-mini]
"""


def test_inputs_are_name_value_pairs_and_a_value_may_hold_an_equals_sign() -> None:
    assert parse_inputs(["question=How long?", "q2=a=b"]) == {"question": "How long?", "q2": "a=b"}


@pytest.mark.parametrize("bad", ["novalue", "=x"])
def test_an_input_without_a_name_or_a_value_is_refused_with_how_to_write_it(bad: str) -> None:
    with pytest.raises(CliError, match="name=value"):
        parse_inputs([bad])


def test_prompts_with_the_same_group_share_a_project_and_the_others_keep_their_own(tmp_path: Path) -> None:
    path = tmp_path / "verano.yaml"
    path.write_text(GROUPED, encoding="utf-8")
    names = {p.entry.name: p.project_name for p in load(path).prompts}
    assert names["classify"] == names["summarise"] == f"support-bot{SEPARATOR}tickets"
    assert names["alone"] == f"support-bot{SEPARATOR}alone"
