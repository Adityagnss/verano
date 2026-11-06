"""
What each chosen model accepts when it is run (ADR 0039), for the Run step: the sampling settings it takes with their
ranges, whether it has a reasoning effort (and which values), and which response formats it can be asked for. Pure:
built from the model's profile and the provider catalog, the same data the checks at start-up use.
"""

import re
import uuid

from pydantic import BaseModel

from app.modules.engine.schemas import ResponseFormatKind
from app.modules.registry.schemas import ModelProfileOut, ParameterRange, ProviderCatalog


class ModelRunOptions(BaseModel):
    model_profile_id: uuid.UUID
    display_name: str
    parameters: dict[str, ParameterRange]
    seed: bool
    reasoning_efforts: list[str]
    response_formats: list[ResponseFormatKind]


class RunOptionsOut(BaseModel):
    max_param_sets: int
    models: list[ModelRunOptions]


def model_options(catalog: ProviderCatalog, profile: ModelProfileOut) -> ModelRunOptions:
    provider = catalog.providers.get(profile.provider)
    spec = provider.run_parameters if provider else None
    thinks = spec is not None and any(re.search(p, profile.model_name) for p in spec.reasoning_models)
    formats = [ResponseFormatKind.TEXT]
    if profile.supports_json_mode:
        formats.append(ResponseFormatKind.JSON_OBJECT)
        if spec is not None and spec.json_schema:
            formats.append(ResponseFormatKind.JSON_SCHEMA)
    return ModelRunOptions(
        model_profile_id=profile.id,
        display_name=profile.display_name,
        parameters=profile.parameters,
        seed="seed" in profile.parameters,
        reasoning_efforts=list(spec.reasoning_efforts) if spec is not None and thinks else [],
        response_formats=formats,
    )
