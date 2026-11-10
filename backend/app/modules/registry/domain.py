"""
Pure registry logic: chat filtering, listing field extraction and model profile building.

A model profile merges four sources with a fixed precedence, highest first:
`model_overrides.yaml` → the provider's own listing → LiteLLM's bundled metadata → the
provider spec defaults. Each attribute takes the first source that knows it, so a price is
never invented: when no source knows it, the profile says "unknown" (NULL), and only
providers marked `free` in the catalog get an explicit $0. No I/O and no provider names.
"""

import re
from decimal import Decimal
from typing import TypeVar

from app.modules.registry.schemas import (
    Capability,
    ChatRule,
    ListingSpec,
    ModelMetadata,
    ModelOverride,
    ParameterRange,
    PriceSource,
    ProfileDraft,
    ProviderCatalog,
    ProviderSpec,
    RawModel,
)

T = TypeVar("T")
PER_MILLION = Decimal(1_000_000)
PRICE_UNIT_TO_PER_MILLION = {"per_token": PER_MILLION, "per_million_tokens": Decimal(1)}
ZERO = Decimal(0)


def first_known(*values: T | None) -> T | None:
    return next((value for value in values if value is not None), None)


def key_last4(key: str) -> str:
    return key[-4:]


def dig(item: object, path: str) -> object:
    current = item
    for part in (p for p in path.split(".") if p):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def rule_matches(item: object, rule: ChatRule) -> bool:
    value = dig(item, rule.path)
    if rule.contains is not None:
        return isinstance(value, list | str) and rule.contains in value
    return value == rule.equals


def to_price_per_mtok(value: object, unit: str) -> Decimal | None:
    if value is None or value == "":
        return None
    price = Decimal(str(value)) * PRICE_UNIT_TO_PER_MILLION[unit]
    return price if price >= ZERO else None


def as_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    if isinstance(value, str):
        return int(value) if value.isdigit() else None
    return int(value)


def raw_model_from_listing(item: dict[str, object], listing: ListingSpec) -> RawModel:
    fields = listing.fields
    get = {name: dig(item, path) for name, path in fields.items()}
    supported = get.get("supported_parameters")
    chat = all(rule_matches(item, rule) for rule in listing.chat_rules)
    return RawModel(
        id=str(item["id"]),
        display_name=str(get["display_name"]) if get.get("display_name") else None,
        context_window=as_int(get.get("context_window")),
        max_output_tokens=as_int(get.get("max_output_tokens")),
        input_price_per_mtok=to_price_per_mtok(get.get("input_price"), listing.price_unit),
        output_price_per_mtok=to_price_per_mtok(get.get("output_price"), listing.price_unit),
        capabilities={Capability.CHAT if chat else Capability.OTHER} if listing.chat_rules else None,
        supported_parameters=[str(p) for p in supported] if isinstance(supported, list) else None,
    )


def is_chat_model(raw: RawModel, spec: ProviderSpec, metadata: ModelMetadata | None) -> bool:
    model_id = raw.id.lower()
    if any(pattern.lower() in model_id for pattern in spec.exclude_id_patterns):
        return False
    if raw.capabilities is not None:
        return Capability.CHAT in raw.capabilities
    if metadata is not None and metadata.mode is not None:
        return metadata.mode == "chat"
    return True


def merge_range(*ranges: ParameterRange | None) -> ParameterRange:
    known = [r for r in ranges if r is not None]
    return ParameterRange(
        min=first_known(*(r.min for r in reversed(known))),
        max=first_known(*(r.max for r in reversed(known))),
    )


def _supported_names(
    raw: RawModel, metadata: ModelMetadata | None, catalog: ProviderCatalog, spec: ProviderSpec
) -> set[str]:
    """What a model accepts: its listing, else every ordinary parameter. Opt-in ones need a say-so."""
    listed = first_known(raw.supported_parameters, metadata.supported_parameters if metadata else None)
    opt_in = set(catalog.opt_in_parameters)
    ordinary = (set(catalog.tunable_parameters) - opt_in) | {catalog.json_mode_parameter}
    names = ordinary if listed is None else set(listed)
    return names | (opt_in & set(spec.extra_parameters))


def build_parameters(
    catalog: ProviderCatalog,
    spec: ProviderSpec,
    raw: RawModel,
    metadata: ModelMetadata | None,
    override: ModelOverride,
    max_output_tokens: int | None,
) -> dict[str, ParameterRange]:
    supported = _supported_names(raw, metadata, catalog, spec)
    unsupported = set(spec.unsupported_parameters) | set(override.unsupported_parameters)
    for rule in spec.model_rules:
        if re.search(rule.pattern, raw.id):
            unsupported |= set(rule.unsupported_parameters)
    parameters = {
        name: merge_range(
            base, spec.parameter_ranges.get(name), raw.parameter_ranges.get(name), override.parameters.get(name)
        )
        for name, base in catalog.tunable_parameters.items()
        if name in supported and name not in unsupported
    }
    if "max_tokens" in parameters and max_output_tokens:
        parameters["max_tokens"] = parameters["max_tokens"].model_copy(update={"max": float(max_output_tokens)})
    return parameters


def resolve_price(
    spec: ProviderSpec, raw: RawModel, metadata: ModelMetadata | None, override: ModelOverride
) -> tuple[Decimal | None, Decimal | None, PriceSource]:
    candidates: list[tuple[Decimal | None, Decimal | None, PriceSource]] = [
        (override.input_price_per_mtok, override.output_price_per_mtok, PriceSource.OVERRIDE),
        (raw.input_price_per_mtok, raw.output_price_per_mtok, PriceSource.PROVIDER),
    ]
    if metadata is not None:
        candidates.append((metadata.input_price_per_mtok, metadata.output_price_per_mtok, PriceSource.LITELLM))
    if spec.free:
        candidates.insert(1, (ZERO, ZERO, PriceSource.FREE))
    for input_price, output_price, source in candidates:
        if input_price is not None and output_price is not None:
            # A table that says a paid model costs nothing is a placeholder, not a price: show it as unknown.
            if input_price == ZERO and output_price == ZERO and source is PriceSource.LITELLM and not spec.free:
                continue
            return input_price, output_price, source
    return None, None, PriceSource.UNKNOWN


def build_profile(
    catalog: ProviderCatalog,
    spec: ProviderSpec,
    raw: RawModel,
    metadata: ModelMetadata | None,
    override: ModelOverride | None,
) -> ProfileDraft:
    override = override or ModelOverride()
    max_output = first_known(
        override.max_output_tokens, raw.max_output_tokens, metadata.max_output_tokens if metadata else None
    )
    parameters = build_parameters(catalog, spec, raw, metadata, override, max_output)
    input_price, output_price, source = resolve_price(spec, raw, metadata, override)
    system_prompt = first_known(metadata.supports_system_messages if metadata else None, True)
    return ProfileDraft(
        model_name=raw.id,
        display_name=raw.display_name or raw.id,
        litellm_model=litellm_model(spec, raw.id),
        context_window=first_known(
            override.context_window, raw.context_window, metadata.context_window if metadata else None
        ),
        max_output_tokens=max_output,
        parameters=parameters,
        supports_json_mode=catalog.json_mode_parameter in _supported_names(raw, metadata, catalog, spec)
        and catalog.json_mode_parameter not in override.unsupported_parameters,
        supports_system_prompt=bool(system_prompt),
        input_price_per_mtok=input_price,
        output_price_per_mtok=output_price,
        price_source=source,
    )


def litellm_model(spec: ProviderSpec, model_name: str) -> str:
    return f"{spec.litellm_prefix}/{model_name}"
