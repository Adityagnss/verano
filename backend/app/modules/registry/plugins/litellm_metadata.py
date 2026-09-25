"""
LiteLLM metadata adapter.

The only place the registry touches LiteLLM: reads its bundled model metadata (context
window, output limit, per-token prices, mode) and its per-provider list of supported
OpenAI-style parameters, converting both into a `ModelMetadata`. Unknown models return
None instead of raising, so discovery never fails because upstream metadata is missing.
"""

from decimal import Decimal

import litellm

from app.modules.registry.schemas import ModelMetadata

PER_MILLION = Decimal(1_000_000)


def _per_mtok(value: object) -> Decimal | None:
    return Decimal(str(value)) * PER_MILLION if isinstance(value, int | float) else None


def lookup_metadata(litellm_model: str) -> ModelMetadata | None:
    prefix, _, model = litellm_model.partition("/")
    try:
        info: dict[str, object] | None = dict(litellm.get_model_info(litellm_model))
    except Exception:
        info = None
    try:
        supported = litellm.get_supported_openai_params(model=model, custom_llm_provider=prefix)
    except Exception:
        supported = None
    if info is None and supported is None:
        return None
    info = info or {}
    max_input = info.get("max_input_tokens")
    max_output = info.get("max_output_tokens")
    system = info.get("supports_system_messages")
    return ModelMetadata(
        mode=str(info["mode"]) if info.get("mode") else None,
        context_window=max_input if isinstance(max_input, int) else None,
        max_output_tokens=max_output if isinstance(max_output, int) else None,
        input_price_per_mtok=_per_mtok(info.get("input_cost_per_token")),
        output_price_per_mtok=_per_mtok(info.get("output_cost_per_token")),
        supported_parameters=list(supported) if supported else None,
        supports_system_messages=system if isinstance(system, bool) else None,
    )
