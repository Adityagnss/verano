"""Every check chosen by default can produce a score: a judged one always says what to judge (the comparison page found
`answer_relevancy` in the default set with no criteria, so it never applied)."""

from pathlib import Path

import pytest

from app.core.datafiles import load_yaml
from app.modules.evaluation.plugins.rules import RULES
from app.modules.generator.domain import EvaluatorCatalog, EvaluatorTemplate

CATALOG = Path(__file__).parents[3] / "app" / "modules" / "evaluation" / "config" / "catalog.yaml"


def templates() -> list[tuple[str, EvaluatorTemplate]]:
    catalog = load_yaml(CATALOG, EvaluatorCatalog)
    found = [("constraints", catalog.constraints)]
    found += [(task, t) for task, items in catalog.task_types.items() for t in items]
    return [(f"{task}/{t.name}", t) for task, t in found]


@pytest.mark.parametrize(("name", "template"), templates(), ids=[n for n, _ in templates()])
def test_a_default_check_can_score(name: str, template: EvaluatorTemplate) -> None:
    if template.kind == "rule":
        assert template.name in RULES, name
    else:
        criteria = str(template.config.get("criteria") or "").strip()
        assert criteria or template.config.get("evaluation_steps"), f"{name} would never apply: it has no criteria"
