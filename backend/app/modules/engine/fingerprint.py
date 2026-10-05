"""
The configuration of an experiment, as one fingerprint and one grouped description
(DEVELOPMENT.md H2 step 2).

The fingerprint is computed from what an experiment already stores (never saved), so older
experiments have one too and a change to the rules can't leave stale values behind. Two
experiments with the same fingerprint were set up the same way: same prompt, dataset and
evaluator versions, the same models with the same settings and runs, the same split and judge.
That makes them *replicable* against each other; it says nothing about whether the answers
match (*stable*), which depends on the provider.

Left out on purpose: the name, the budget cap and the origin (they don't change what is
asked), and settings a model ignores (they never reach it, so they don't change the call).
"""

import hashlib
import json
from typing import Any

from pydantic import ValidationError

from app.modules.engine.models import Experiment
from app.modules.engine.sampling import normalize_params
from app.modules.engine.schemas import ModelSetting, RunConfiguration

VERSION = 1
SHORT = 8


def _profiles(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(profile["id"]): profile for profile in snapshot.get("profiles", [])}


def _sent(params: dict[str, Any], profile: dict[str, Any] | None) -> dict[str, Any]:
    """The settings that reach the model, in their normal form."""
    accepted = set(profile["parameters"]) if profile else set(params)
    kept = {name: value for name, value in params.items() if name in accepted}
    try:
        return normalize_params(kept)
    except ValidationError:
        return kept


def model_settings(row: Experiment) -> list[ModelSetting]:
    profiles = _profiles(row.snapshot)
    settings = []
    for entry in row.config.get("models", []):
        profile = profiles.get(str(entry["model_profile_id"]))
        params = entry.get("params", {})
        sent = _sent(params, profile)
        settings.append(
            ModelSetting(
                model_profile_id=entry["model_profile_id"],
                display_name=entry.get("display_name") or (profile or {}).get("display_name", ""),
                provider=(profile or {}).get("provider", ""),
                model=(profile or {}).get("model_name", ""),
                runs=entry["runs"],
                params=sent,
                ignored_params=sorted(set(params) - set(sent)),
            )
        )
    return settings


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def config_hash(row: Experiment) -> str:
    models = sorted(
        ({"provider": m.provider, "model": m.model, "runs": m.runs, "params": m.params} for m in model_settings(row)),
        key=_canonical,
    )
    judge = row.config.get("judge")
    payload = {
        "v": VERSION,
        "prompt": str(row.prompt_version_id),
        "dataset": str(row.dataset_version_id),
        "evaluators": str(row.evaluator_set_version_id),
        "split": str(row.split_scope.value),
        "models": models,
        "judge": judge["model"] if judge else None,
    }
    return hashlib.sha256(_canonical(payload).encode()).hexdigest()


def run_configuration(row: Experiment, prompt_version: int | None = None) -> RunConfiguration:
    judge = row.config.get("judge")
    return RunConfiguration(
        hash=config_hash(row),
        prompt_version_id=row.prompt_version_id,
        prompt_version=prompt_version,
        dataset_version_id=row.dataset_version_id,
        evaluator_set_version_id=row.evaluator_set_version_id,
        split_scope=row.split_scope,
        judge_model=judge["model"] if judge else None,
        models=model_settings(row),
        libraries=row.snapshot.get("libraries", {}),
    )
