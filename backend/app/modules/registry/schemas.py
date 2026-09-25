"""
Registry schemas: the provider catalog (YAML), discovered models, profiles and the API.

`ProviderCatalog` validates `config/providers.yaml`; `ModelOverrides` validates
`config/model_overrides.yaml`. `RawModel` is what a provider plugin returns from its
listing endpoint, before profile building. `CallTarget` is what the gateway receives for
one call: everything needed to reach the model, including the decrypted key, which never
leaves the process and is never serialized into a response.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_serializer


class ParameterRange(BaseModel):
    min: float | None = None
    max: float | None = None


class RateLimits(BaseModel):
    rpm: int = Field(gt=0)
    tpm: int = Field(gt=0)


class ChatRule(BaseModel):
    path: str
    equals: object | None = None
    contains: str | None = None


class ListingSpec(BaseModel):
    items_path: str = "data"
    fields: dict[str, str] = {}
    price_unit: str = "per_token"
    chat_rules: list[ChatRule] = []


class ProviderSpec(BaseModel):
    display_name: str
    client: str
    litellm_prefix: str
    base_url: str | None = None
    base_url_setting: str | None = None
    api_version: str | None = None
    requires_key: bool
    free: bool = False
    enabled_setting: str | None = None
    listing: ListingSpec = ListingSpec()
    exclude_id_patterns: list[str] = []
    auth_error_markers: list[str] = []
    parameter_ranges: dict[str, ParameterRange] = {}
    unsupported_parameters: list[str] = []
    rate_limits: RateLimits


class RateLimitHeaders(BaseModel):
    limit_requests: list[str] = []
    remaining_requests: list[str] = []
    limit_tokens: list[str] = []
    remaining_tokens: list[str] = []
    retry_after: list[str] = []


class ProviderCatalog(BaseModel):
    tunable_parameters: dict[str, ParameterRange]
    json_mode_parameter: str
    rate_limit_headers: RateLimitHeaders
    providers: dict[str, ProviderSpec]


class ModelOverride(BaseModel):
    context_window: int | None = None
    max_output_tokens: int | None = None
    input_price_per_mtok: Decimal | None = None
    output_price_per_mtok: Decimal | None = None
    parameters: dict[str, ParameterRange] = {}
    unsupported_parameters: list[str] = []


class ModelOverrides(BaseModel):
    models: dict[str, ModelOverride] = {}


class Capability(StrEnum):
    CHAT = "chat"
    EMBEDDING = "embedding"
    OTHER = "other"


class RawModel(BaseModel):
    id: str
    display_name: str | None = None
    context_window: int | None = None
    max_output_tokens: int | None = None
    input_price_per_mtok: Decimal | None = None
    output_price_per_mtok: Decimal | None = None
    capabilities: set[Capability] | None = None
    supported_parameters: list[str] | None = None
    parameter_ranges: dict[str, ParameterRange] = {}


class ModelMetadata(BaseModel):
    mode: str | None = None
    context_window: int | None = None
    max_output_tokens: int | None = None
    input_price_per_mtok: Decimal | None = None
    output_price_per_mtok: Decimal | None = None
    supported_parameters: list[str] | None = None
    supports_system_messages: bool | None = None


class PriceSource(StrEnum):
    OVERRIDE = "override"
    PROVIDER = "provider"
    LITELLM = "litellm"
    FREE = "free"
    UNKNOWN = "unknown"


class CredentialStatus(StrEnum):
    VALID = "valid"
    INVALID = "invalid"


class ProfileDraft(BaseModel):
    model_name: str
    display_name: str
    litellm_model: str
    context_window: int | None
    max_output_tokens: int | None
    parameters: dict[str, ParameterRange]
    supports_json_mode: bool
    supports_system_prompt: bool
    input_price_per_mtok: Decimal | None
    output_price_per_mtok: Decimal | None
    price_source: PriceSource


class ProviderOut(BaseModel):
    name: str
    display_name: str
    requires_key: bool
    default_base_url: str | None
    free: bool


class CredentialCreate(BaseModel):
    provider: str
    api_key: SecretStr | None = None
    base_url: str | None = None
    label: str | None = Field(default=None, max_length=120)
    rpm_limit: int | None = Field(default=None, gt=0)
    tpm_limit: int | None = Field(default=None, gt=0)


class CredentialUpdate(BaseModel):
    label: str | None = Field(default=None, max_length=120)
    rpm_limit: int | None = Field(default=None, gt=0)
    tpm_limit: int | None = Field(default=None, gt=0)


class CredentialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: str
    label: str | None
    key_last4: str | None
    base_url: str | None
    status: CredentialStatus
    rpm_limit: int | None
    tpm_limit: int | None
    model_count: int
    last_validated_at: datetime | None
    created_at: datetime


class ModelProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    credential_id: uuid.UUID
    provider: str
    model_name: str
    display_name: str
    litellm_model: str
    context_window: int | None
    max_output_tokens: int | None
    parameters: dict[str, ParameterRange]
    supports_json_mode: bool
    supports_system_prompt: bool
    input_price_per_mtok: Decimal | None
    output_price_per_mtok: Decimal | None
    price_source: PriceSource
    price_known: bool
    is_selected: bool

    @field_serializer("input_price_per_mtok", "output_price_per_mtok")
    def _plain_price(self, value: Decimal | None) -> str | None:
        return None if value is None else f"{value.normalize():f}"


class ModelSelection(BaseModel):
    selected: list[uuid.UUID] = []
    unselected: list[uuid.UUID] = []


class CallTarget(BaseModel):
    credential_id: uuid.UUID
    provider: str
    provider_display_name: str
    api_key: SecretStr | None
    api_base: str | None
    profile: ModelProfileOut
    default_limits: RateLimits
    override_rpm: int | None
    override_tpm: int | None
