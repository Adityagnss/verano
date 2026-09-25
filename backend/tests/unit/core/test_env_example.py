"""Guards the rule that every setting is documented in .env.example (ENGINEERING_STANDARDS 11.8)."""

import re
from pathlib import Path

import pytest

from app.core.config import Settings

pytestmark = pytest.mark.unit

ENV_EXAMPLE = Path(__file__).resolve().parents[4] / ".env.example"
KEY = re.compile(r"^#?\s*([A-Z][A-Z0-9_]*)=", re.MULTILINE)
COMPOSE_ONLY = {
    "POSTGRES_PASSWORD",
    "VERANO_SITE_ADDRESS",
    "VERANO_HTTP_PORT",
    "VERANO_HTTPS_PORT",
    "VERANO_DOCKER_SUBNET",
    "CADDY_ADDRESS",
}


def env_name(field: str) -> str:
    alias = Settings.model_fields[field].validation_alias
    choices = getattr(alias, "choices", None)
    return str(choices[0]) if choices else f"VERANO_{field.upper()}"


def test_every_setting_is_listed_in_env_example_and_nothing_stale_is() -> None:
    documented = set(KEY.findall(ENV_EXAMPLE.read_text())) - COMPOSE_ONLY
    assert documented == {env_name(field) for field in Settings.model_fields}
