"""
The judge gallery (ADR 0020): ready-made judged checks loaded from `config/judges.yaml`.

Each entry is data: a title, a description, the instruction the judge is given (visible and editable once added to
a project), what a case must carry for it to apply, and its measured agreement with people. An entry whose
agreement was never measured says so. `as_config` turns an entry into the config of an evaluator, so adding a judge
to a project is the same as adding any other judged check.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.core.datafiles import load_yaml

GALLERY_PATH = Path(__file__).parent / "config" / "judges.yaml"
NOT_MEASURED = "Agreement with people not yet measured."


class MeasuredAgreement(BaseModel):
    model: str
    date: str
    answers: int
    raw: float
    kappa: float | None = None


class JudgeEntry(BaseModel):
    title: str
    description: str
    requires: str | None = None
    include_tool_calls: bool = False
    threshold: float
    criteria: str
    limits: str
    agreement: MeasuredAgreement | None = None


class Gallery(BaseModel):
    generic_limits: dict[str, str]
    judges: dict[str, JudgeEntry]


@lru_cache(maxsize=1)
def gallery() -> Gallery:
    return load_yaml(GALLERY_PATH, Gallery)


def as_config(name: str, entry: JudgeEntry) -> dict[str, Any]:
    """The evaluator config for adding this judge to a project."""
    config: dict[str, Any] = {"kind": "deepeval", "metric": "g_eval", "criteria": entry.criteria, "gallery": name}
    if entry.requires:
        config["requires"] = entry.requires
    if entry.include_tool_calls:
        config["include_tool_calls"] = True
    return config
