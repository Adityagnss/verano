"""Unit tests for model profile building: price precedence, chat filtering and parameter ranges."""

from decimal import Decimal

import pytest

from app.modules.registry.domain import build_profile, is_chat_model, raw_model_from_listing
from app.modules.registry.schemas import (
    Capability,
    ChatRule,
    ListingSpec,
    ModelMetadata,
    ModelOverride,
    ParameterRange,
    PriceSource,
    ProviderCatalog,
    ProviderSpec,
    RateLimitHeaders,
    RateLimits,
    RawModel,
)

pytestmark = [pytest.mark.unit, pytest.mark.registry]

CATALOG = ProviderCatalog(
    tunable_parameters={"temperature": ParameterRange(min=0, max=2), "max_tokens": ParameterRange(min=1), "seed": {}},
    json_mode_parameter="response_format",
    rate_limit_headers=RateLimitHeaders(),
    providers={},
)


def spec(**overrides: object) -> ProviderSpec:
    base = {
        "display_name": "P",
        "client": "c",
        "litellm_prefix": "p",
        "requires_key": True,
        "rate_limits": RateLimits(rpm=1, tpm=1),
    }
    return ProviderSpec.model_validate({**base, **overrides})


METADATA = ModelMetadata(
    mode="chat",
    context_window=128_000,
    max_output_tokens=16_384,
    input_price_per_mtok=Decimal("0.15"),
    output_price_per_mtok=Decimal("0.60"),
    supported_parameters=["temperature", "max_tokens", "response_format"],
)


def test_price_precedence_is_override_then_provider_listing_then_litellm() -> None:
    raw = RawModel(id="m", input_price_per_mtok=Decimal(1), output_price_per_mtok=Decimal(2))
    override = ModelOverride(input_price_per_mtok=Decimal(9), output_price_per_mtok=Decimal(9))
    assert build_profile(CATALOG, spec(), raw, METADATA, override).price_source is PriceSource.OVERRIDE
    listed = build_profile(CATALOG, spec(), raw, METADATA, None)
    assert (listed.input_price_per_mtok, listed.price_source) == (Decimal(1), PriceSource.PROVIDER)
    from_litellm = build_profile(CATALOG, spec(), RawModel(id="m"), METADATA, None)
    assert (from_litellm.output_price_per_mtok, from_litellm.price_source) == (Decimal("0.60"), PriceSource.LITELLM)


def test_unknown_price_stays_unknown_and_only_free_providers_are_zero() -> None:
    unknown = build_profile(CATALOG, spec(), RawModel(id="m"), None, None)
    assert (unknown.input_price_per_mtok, unknown.price_source) == (None, PriceSource.UNKNOWN)
    local = build_profile(CATALOG, spec(free=True), RawModel(id="m"), None, None)
    assert (local.input_price_per_mtok, local.price_source) == (Decimal(0), PriceSource.FREE)


def test_parameters_are_limited_to_what_the_model_supports_with_merged_ranges() -> None:
    provider = spec(parameter_ranges={"temperature": {"max": 1.0}})
    profile = build_profile(CATALOG, provider, RawModel(id="m"), METADATA, None)
    assert set(profile.parameters) == {"temperature", "max_tokens"}
    assert profile.parameters["temperature"] == ParameterRange(min=0, max=1.0)
    assert profile.parameters["max_tokens"].max == 16_384
    assert profile.supports_json_mode
    no_temperature = build_profile(
        CATALOG, provider, RawModel(id="m"), METADATA, ModelOverride(unsupported_parameters=["temperature"])
    )
    assert "temperature" not in no_temperature.parameters


def test_chat_filter_uses_exclusions_then_listing_capabilities_then_metadata_mode() -> None:
    provider = spec(exclude_id_patterns=["embedding"])
    assert not is_chat_model(RawModel(id="text-embedding-3-small"), provider, None)
    assert not is_chat_model(RawModel(id="m", capabilities={Capability.OTHER}), provider, METADATA)
    assert not is_chat_model(RawModel(id="m"), provider, METADATA.model_copy(update={"mode": "audio_speech"}))
    assert is_chat_model(RawModel(id="brand-new-model"), provider, None)


def test_listing_fields_and_chat_rules_are_read_from_the_declared_paths() -> None:
    listing = ListingSpec(
        fields={
            "context_window": "context_length",
            "input_price": "pricing.prompt",
            "output_price": "pricing.completion",
        },
        price_unit="per_token",
        chat_rules=[ChatRule(path="architecture.output_modalities", contains="text")],
    )
    item = {
        "id": "x",
        "context_length": 8192,
        "pricing": {"prompt": "0.000001", "completion": "0.000002"},
        "architecture": {"output_modalities": ["image"]},
    }
    raw = raw_model_from_listing(item, listing)
    assert (raw.context_window, raw.input_price_per_mtok, raw.output_price_per_mtok) == (8192, Decimal(1), Decimal(2))
    assert raw.capabilities == {Capability.OTHER}
