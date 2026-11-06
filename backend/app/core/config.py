"""
Application settings.

The single source of every environment-dependent value and tunable threshold. Values are
read from the environment and `.env` with the `VERANO_` prefix; `OLLAMA_BASE_URL` is also
accepted unprefixed because it is the name the Ollama ecosystem already uses. Every field
is mirrored, with its default and a one-line description, in the repository's
`.env.example`. Everything else imports settings through `get_settings()`, which caches
one instance per process; tests build their own `Settings` and inject it.
With VERANO_ENVIRONMENT=production, settings that only make sense for local development
(a non-Secure refresh cookie, the mock provider) are refused at startup.
"""

from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_DIR = Path(__file__).resolve().parent.parent
PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="VERANO_", extra="ignore")

    app_name: str = "Verano"
    environment: str = "development"
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = []
    log_level: str = "INFO"
    log_redact_patterns: list[str] = [
        r"sk-[A-Za-z0-9_\-]{8,}",
        r"AIza[0-9A-Za-z_\-]{20,}",
        r"gsk_[A-Za-z0-9]{8,}",
        r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}",
    ]

    database_url: str = "postgresql+asyncpg://verano:verano@localhost:5432/verano"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    valkey_url: str = "redis://localhost:6379/0"

    master_keys: SecretStr = SecretStr("")
    jwt_secret: SecretStr = SecretStr("")
    jwt_algorithm: str = "HS256"
    access_token_ttl_s: int = 900
    refresh_token_ttl_s: int = 60 * 60 * 24 * 30
    refresh_cookie_name: str = "verano_refresh"
    refresh_cookie_secure: bool = True
    password_min_length: int = 10
    allow_signup: bool = True
    auth_rate_window_s: int = 60
    auth_rate_limit_per_ip: int = 20
    auth_rate_limit_per_email: int = 5
    trusted_proxies: list[str] = []
    personal_org_name_template: str = "{name}'s workspace"

    pagination_default_limit: int = 50
    pagination_max_limit: int = 200

    ollama_base_url: str = Field(
        default="http://host.docker.internal:11434",
        validation_alias=AliasChoices("OLLAMA_BASE_URL", "VERANO_OLLAMA_BASE_URL"),
    )
    mock_provider_enabled: bool = False
    mock_models_path: Path = APP_DIR / "modules/gateway/config/mock_models.yaml"
    mock_scripted_dir: Path = APP_DIR / "modules/gateway/config/mock_scripted"
    mock_answer_key_path: Path = APP_DIR / "modules/gateway/config/mock_answer_key.yaml"

    providers_path: Path = APP_DIR / "modules/registry/config/providers.yaml"
    model_overrides_path: Path = APP_DIR / "modules/registry/config/model_overrides.yaml"
    provider_http_timeout_s: float = 15.0

    llm_timeout_s: float = 60.0
    # long writing and grouping calls (Improve), which a reasoning model may need minutes for
    assistant_timeout_s: float = 240.0
    llm_max_attempts: int = 3
    llm_backoff_base_s: float = 0.5
    llm_backoff_max_s: float = 30.0
    json_repair_attempts: int = 1
    prompt_template_max_chars: int = 200_000

    storage_backend: str = "local"
    storage_root: Path = APP_DIR.parent / "data"
    upload_max_bytes: int = 100_000_000
    upload_max_rows: int = 200_000
    file_parse_timeout_s: float = 300.0
    job_hard_limit_grace_s: float = 30.0
    csv_field_max_chars: int = 1_000_000
    zip_max_uncompressed_bytes: int = 1_000_000_000
    zip_max_entries: int = 10_000
    zip_max_ratio: float = 200.0
    document_max_pages: int = 500
    document_section_max_chars: int = 3_000
    profile_sample_rows: int = 20
    attachment_max_chars: int = 200_000
    attachment_max_distinct: int = 100_000
    attachment_example_values: int = 10
    report_max_listed_rows: int = 100
    import_batch_size: int = 1_000
    progress_every_rows: int = 2_000
    progress_ttl_s: int = 86_400
    sse_keepalive_s: float = 15.0
    dataset_default_category: str = "happy_path"
    dataset_default_name: str = "Test cases"
    dataset_holdout_ratio: float = 0.3
    dataset_min_holdout: int = 15
    generator_default_size: int = 50
    generator_confirm_cost: Decimal = Decimal("0.25")
    generator_batch_size: int = 10
    generator_example_rows: int = 5
    generator_task_spec_rows: int = 10
    generator_max_sections: int = 8
    generator_section_chars: int = 1_500
    generator_answer_batch_size: int = 20
    generator_top_up_rounds: int = 2
    generator_timeout_s: float = 3_600.0
    embedder: str = "fastembed"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_cache_dir: Path = APP_DIR.parent / "data" / "models"
    dedupe_similarity: float = 0.92
    engine_chunk_size: int = 50
    engine_provider_concurrency: int = 8
    engine_chunk_timeout_s: float = 1_800.0
    judge_concurrency: int = 24
    evaluation_timeout_s: float = 3_600.0
    document_max_chars: int = 5_000_000
    token_estimate_chars_per_token: int = 4

    # Phase 6: labels, agreement, judge cache, stored answers, code checks
    disabled_features: list[str] = []
    label_min_for_agreement: int = 20
    agreement_min_raw: float = 0.8
    agreement_min_kappa: float = 0.6
    compare_min_cases: int = 10
    stored_answer_max_chars: int = 200_000
    judge_cache_enabled: bool = True
    judge_cache_recent_size: int = 2_048
    sandbox_url: str | None = None
    sandbox_wall_s: float = 5.0
    sandbox_cpu_s: int = 3
    sandbox_memory_mb: int = 256
    sandbox_output_chars: int = 2_000
    # Phase 7: apps under test
    app_allowed_hosts: list[str] = []
    app_timeout_s: float = 60.0
    app_concurrency: int = 5
    app_retry_attempts: int = 0
    app_response_max_bytes: int = 2_000_000
    app_max_redirects: int = 3
    conversation_max_turns: int = 8

    rate_limit_decrease_factor: float = 0.5
    rate_limit_increase_fraction: float = 0.05
    rate_limit_floor_fraction: float = 0.05
    rate_limit_acquire_timeout_s: float = 120.0
    rate_limit_state_ttl_s: int = 3600

    # Phase 8 (shipit): prompt labels, serving prompts to apps
    prompt_labels_max: int = 20
    prompt_label_history_depth: int = 200

    @model_validator(mode="after")
    def _production_is_locked_down(self) -> "Settings":
        if self.environment != PRODUCTION:
            return self
        if not self.refresh_cookie_secure:
            raise ValueError("VERANO_REFRESH_COOKIE_SECURE must be true when VERANO_ENVIRONMENT=production")
        if self.mock_provider_enabled:
            raise ValueError("VERANO_MOCK_PROVIDER_ENABLED must be false when VERANO_ENVIRONMENT=production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
