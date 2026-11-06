"""
Provider-specific run parameters (ADR 0039): which settings a model really accepts beyond plain sampling.

Some settings only exist for some providers or models: a reasoning effort, top-k, a JSON response format.
Sending one to a model that does not take it would either fail late or be ignored without a word, so each is checked
when the experiment is set up and refused with a plain message. Rules are plugins registered by the provider's
`client` name (a new provider with its own quirks adds one class here and names it); what a provider accepts is data
in `providers.yaml` (`run_parameters`). A provider with no class of its own uses the default rules.
"""

import re
from typing import Any, Protocol

from app.core.registry import Registry
from app.modules.registry.schemas import ModelProfileOut, ProviderCatalog, RunParameterSpec

REASONING = "reasoning_effort"
FORMAT = "response_format"
JSON_OBJECT = "json_object"
JSON_SCHEMA = "json_schema"
# Settings checked here. Plain sampling settings (temperature, top_p, max_tokens, stop, penalties) keep their
# older behaviour: a setting the model ignores is listed as ignored, with its range checked.
PROVIDER_SPECIFIC = ("top_k", REASONING, FORMAT)
# Settings that reach LiteLLM although a model's profile does not list them (the profile lists plain sampling).
PASSTHROUGH = frozenset({REASONING})

NO_TOP_K = "{model} does not accept top-k. Remove it for this model."
NOT_REASONING = (
    "{model} is not a reasoning model, so it has no reasoning effort. "
    "Remove the reasoning effort for this model, or pick a model that thinks before it answers."
)
BAD_EFFORT = "{model} accepts the reasoning efforts {allowed}, not '{value}'."
NO_JSON = "{model} cannot be told to answer in JSON. Choose free text for this model and check the format with a rule."
NO_SCHEMA = (
    "{model} cannot enforce a JSON schema. Choose 'JSON object' for it, "
    "or free text with the JSON schema check, which reads the answer afterwards."
)
THINKING_BUDGET = {"minimal": 1024, "low": 1024, "medium": 2048, "high": 4096}
NEEDS_ROOM = (
    "With reasoning effort '{value}', {model} needs more than {budget} tokens of room to answer. "
    "Raise the maximum tokens (now {max_tokens}) or lower the reasoning effort."
)
NEEDS_DEFAULT_TEMPERATURE = (
    "{model} only accepts its default temperature while it reasons. Remove the temperature, or the reasoning effort."
)


class RunParameterRules(Protocol):
    def problems(self, profile: ModelProfileOut, spec: RunParameterSpec, params: dict[str, Any]) -> list[str]: ...


RUN_PARAMETER_RULES: Registry[type[RunParameterRules]] = Registry("run parameter rules")


@RUN_PARAMETER_RULES.register("default")
class DefaultRules:
    def problems(self, profile: ModelProfileOut, spec: RunParameterSpec, params: dict[str, Any]) -> list[str]:
        found: list[str] = []
        model = profile.display_name
        if params.get("top_k") is not None and "top_k" not in profile.parameters:
            found.append(NO_TOP_K.format(model=model))
        if params.get(REASONING) is not None:
            found.extend(self.reasoning(profile, spec, params))
        if params.get(FORMAT) is not None:
            found.extend(self.format(profile, spec, params[FORMAT]))
        return found

    def reasoning(self, profile: ModelProfileOut, spec: RunParameterSpec, params: dict[str, Any]) -> list[str]:
        model, value = profile.display_name, str(params[REASONING])
        if not any(re.search(pattern, profile.model_name) for pattern in spec.reasoning_models):
            return [NOT_REASONING.format(model=model)]
        if value not in spec.reasoning_efforts:
            return [BAD_EFFORT.format(model=model, allowed=", ".join(spec.reasoning_efforts), value=value)]
        return []

    @staticmethod
    def format(profile: ModelProfileOut, spec: RunParameterSpec, wanted: dict[str, Any]) -> list[str]:
        model = profile.display_name
        if not profile.supports_json_mode:
            return [NO_JSON.format(model=model)]
        if wanted.get("type") == JSON_SCHEMA and not spec.json_schema:
            return [NO_SCHEMA.format(model=model)]
        return []


@RUN_PARAMETER_RULES.register("anthropic")
class AnthropicRules(DefaultRules):
    """Claude's reasoning is a token budget inside the answer's room, and it fixes the temperature."""

    def reasoning(self, profile: ModelProfileOut, spec: RunParameterSpec, params: dict[str, Any]) -> list[str]:
        found = super().reasoning(profile, spec, params)
        if found:
            return found
        model, value = profile.display_name, str(params[REASONING])
        budget, room = THINKING_BUDGET[value], params.get("max_tokens")
        if room is not None and room <= budget:
            found.append(NEEDS_ROOM.format(value=value, model=model, budget=budget, max_tokens=room))
        if params.get("temperature") not in (None, 1, 1.0):
            found.append(NEEDS_DEFAULT_TEMPERATURE.format(model=model))
        return found


def check_run_parameters(catalog: ProviderCatalog, profile: ModelProfileOut, params: dict[str, Any]) -> list[str]:
    """Every reason this model cannot run with these settings, in plain words; empty when it can."""
    provider = catalog.providers.get(profile.provider)
    if provider is None:
        return []
    name = provider.client if provider.client in RUN_PARAMETER_RULES else "default"
    return RUN_PARAMETER_RULES[name]().problems(profile, provider.run_parameters, params)
