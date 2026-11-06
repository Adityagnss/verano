"""
The columns of an experiment: a model, or a model with one named parameter set (ADR 0039). Pure.

Results, comparisons and progress are keyed by a *column id*. With no parameter sets (or just one) the column id is
the model's profile id, exactly as before, so every older key and link keeps working. With two or more sets each
(model, set) pair gets its own column id, derived from the profile id and the effective settings, so the same model
with the same settings has the same column id in any experiment and can be compared across them.

A set's settings for a model are: the model's own settings, then the set's, then that model's override for the set.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from app.core.errors import ValidationFailed
from app.modules.engine.domain import param_set_key
from app.modules.engine.sampling import normalize_params
from app.modules.engine.schemas import ModelRun, ParamSet

COLUMN_NAMESPACE = uuid.UUID("0c6e1b52-4f0a-4d3e-9b7a-6a1f2d8e9c43")
FORMAT_PARAM = "response_format"
DEFAULT_SET = "Default"
SAME_NAME = "Two parameter sets are both called '{name}'. Give each its own name."
SAME_SETTINGS = "{model}: the sets '{first}' and '{second}' end up with the same settings, so one of them adds nothing."
UNKNOWN_OVERRIDE = "A model has settings for the set '{name}', but there is no set with that name."
TOO_MANY = "A run can compare at most {limit} parameter sets."


@dataclass(frozen=True)
class Column:
    column_id: uuid.UUID
    profile_id: uuid.UUID
    set_name: str | None
    runs: int
    params: dict[str, Any]
    base_params: dict[str, Any]
    overrides: dict[str, Any]


def column_id(profile_id: uuid.UUID, params: dict[str, Any]) -> uuid.UUID:
    return uuid.uuid5(COLUMN_NAMESPACE, f"{profile_id}:{param_set_key(params)}")


def expand_columns(
    models: list[ModelRun], sets: list[ParamSet], limit: int, names: dict[uuid.UUID, str]
) -> list[Column]:
    """One column per model, or per model and set. Refuses repeated names, overrides of unknown sets and sets that
    come out the same for a model."""
    if len(sets) > limit:
        raise ValidationFailed(TOO_MANY.format(limit=limit))
    set_names = [s.name for s in sets]
    for name in set_names:
        if [n.lower() for n in set_names].count(name.lower()) > 1:
            raise ValidationFailed(SAME_NAME.format(name=name))
    columns: list[Column] = []
    for model in models:
        unknown = sorted(set(model.overrides) - set(set_names))
        if unknown:
            raise ValidationFailed(UNKNOWN_OVERRIDE.format(name=unknown[0]))
        if not sets:
            columns.append(
                Column(model.model_profile_id, model.model_profile_id, None, model.runs, model.params, model.params, {})
            )
            continue
        seen: dict[str, str] = {}
        for one in sets:
            override = model.overrides.get(one.name, {})
            effective = normalize_params({**model.params, **one.params, **override})
            key = param_set_key(effective)
            if key in seen:
                raise ValidationFailed(
                    SAME_SETTINGS.format(
                        model=names.get(model.model_profile_id, "A model"), first=seen[key], second=one.name
                    )
                )
            seen[key] = one.name
            identity = model.model_profile_id if len(sets) == 1 else column_id(model.model_profile_id, effective)
            columns.append(
                Column(identity, model.model_profile_id, one.name, model.runs, effective, model.params, override)
            )
    return columns


def with_format(columns: list[Column], response_format: dict[str, Any] | None, skip: set[uuid.UUID]) -> list[Column]:
    """The columns with the run's response format added to their settings (not for the models in `skip`, the apps,
    which are not sent a format)."""
    if response_format is None:
        return columns
    formatted = []
    for c in columns:
        params = c.params if c.profile_id in skip else {**c.params, FORMAT_PARAM: response_format}
        formatted.append(Column(c.column_id, c.profile_id, c.set_name, c.runs, params, c.base_params, c.overrides))
    return formatted


def column_name(display_name: str, set_name: str | None) -> str:
    return f"{display_name} · {set_name}" if set_name else display_name


def request_fields(config: dict[str, Any]) -> dict[str, Any]:
    """The `models`, `param_sets` and `response_format` of an `ExperimentCreate`, rebuilt from a stored
    configuration (older ones have no sets and no format)."""
    models: dict[str, ModelRun] = {}
    for entry in config["models"]:
        profile_id = str(entry.get("profile_id") or entry["model_profile_id"])
        named = entry.get("param_set")
        model = models.setdefault(
            profile_id,
            ModelRun(
                model_profile_id=uuid.UUID(profile_id),
                runs=entry["runs"],
                params=entry.get("base_params", entry["params"]) if named else entry["params"],
            ),
        )
        if named and entry.get("overrides"):
            model.overrides[named] = normalize_params(entry["overrides"])
    return {
        "models": list(models.values()),
        "param_sets": [ParamSet(name=s["name"], params=s["params"]) for s in config.get("param_sets", [])],
        "response_format": config.get("response_format") or "text",
    }
