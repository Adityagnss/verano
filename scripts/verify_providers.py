"""
One-off check of the recorded provider fixtures against the live APIs (DEVELOPMENT.md E2).

Run once before a public release by whoever holds the keys; it is not part of development
or CI. For every provider whose key is set as VERIFY_<PROVIDER>_KEY (for example
VERIFY_OPENAI_KEY), it: lists models through Verano's own provider client, makes one tiny
completion (max_tokens=1) through Verano's LiteLLM adapter, and sends one deliberately bad
key. It prints every place the live response shape differs from the fixture in
backend/tests/fixtures/providers/<provider>/, so the fixtures can be corrected.
Run from backend/: `PYTHONPATH=. uv run python ../scripts/verify_providers.py`.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
from pydantic import SecretStr

from app.core.config import Settings
from app.core.datafiles import load_yaml
from app.core.errors import ProviderAuthError, ProviderError
from app.core.registry import load_plugins
from app.modules.gateway.plugins.litellm_client import LiteLLMClient, configure_litellm
from app.modules.gateway.schemas import Message
from app.modules.registry.domain import litellm_model
from app.modules.registry.plugins.base import PROVIDER_CLIENTS
from app.modules.registry.schemas import CallTarget, ModelProfileOut, PriceSource, ProviderCatalog, ProviderSpec

FIXTURES = Path(__file__).resolve().parent.parent / "backend/tests/fixtures/providers"
BAD_KEY = "sk-verano-verify-deliberately-invalid-0000"
load_plugins("app.modules.registry.plugins")


def first_item(payload: Any) -> dict[str, Any]:
    items = payload if isinstance(payload, list) else next((v for v in payload.values() if isinstance(v, list)), [])
    return items[0] if items and isinstance(items[0], dict) else {}


def shape_differences(provider: str, live: Any) -> list[str]:
    fixture_path = FIXTURES / provider / "models.json"
    if not fixture_path.exists():
        return [f"no fixture at {fixture_path}"]
    recorded = json.loads(fixture_path.read_text())
    differences = []
    if isinstance(live, dict) and isinstance(recorded, dict) and set(live) != set(recorded):
        differences.append(f"top-level keys differ: {sorted(set(live) ^ set(recorded))}")
    item_keys = set(first_item(live)) ^ set(first_item(recorded))
    if item_keys:
        differences.append(f"model item keys differ: {sorted(item_keys)}")
    return differences


def target(provider: str, spec: ProviderSpec, model: str, key: str, base_url: str) -> CallTarget:
    profile = ModelProfileOut.model_validate(
        {
            "id": "00000000-0000-7000-8000-000000000001",
            "credential_id": "00000000-0000-7000-8000-000000000002",
            "provider": provider,
            "model_name": model,
            "display_name": model,
            "litellm_model": litellm_model(spec, model),
            "context_window": None,
            "max_output_tokens": None,
            "parameters": {},
            "supports_json_mode": False,
            "supports_system_prompt": True,
            "input_price_per_mtok": None,
            "output_price_per_mtok": None,
            "price_source": PriceSource.UNKNOWN,
            "price_known": False,
            "is_selected": True,
        }
    )
    return CallTarget(
        credential_id=profile.credential_id,
        provider=provider,
        provider_display_name=spec.display_name,
        api_key=SecretStr(key),
        api_base=base_url,
        profile=profile,
        default_limits=spec.rate_limits,
        override_rpm=None,
        override_tpm=None,
    )


async def verify(provider: str, spec: ProviderSpec, key: str, http: httpx.AsyncClient, settings: Settings) -> list[str]:
    base_url = spec.base_url or ""
    client = PROVIDER_CLIENTS[spec.client](spec, http, settings=settings)
    problems: list[str] = []
    try:
        models = await client.list_models(key, base_url)
    except ProviderError as exc:
        return [f"listing with the real key failed: {exc.message}"]
    if not models:
        problems.append("listing returned no models")
    raw = await http.get(f"{base_url.rstrip('/')}/models", headers={"Authorization": f"Bearer {key}", "x-api-key": key})
    if raw.is_success:
        problems += shape_differences(provider, raw.json())
    chat_model = next((m.id for m in models), None)
    if chat_model:
        try:
            call_target = target(provider, spec, chat_model, key, base_url)
            await LiteLLMClient().acompletion(call_target, [Message(role="user", content="hi")], {"max_tokens": 1}, 30)
        except ProviderError as exc:
            problems.append(f"tiny completion on {chat_model} failed: {exc.message}")
    try:
        await client.list_models(BAD_KEY, base_url)
        problems.append("a bad key was accepted")
    except ProviderAuthError:
        pass
    except ProviderError as exc:
        problems.append(f"a bad key gave {type(exc).__name__} instead of ProviderAuthError: {exc.message}")
    return problems


async def main() -> int:
    configure_litellm()
    settings = Settings(_env_file=None)
    catalog = load_yaml(settings.providers_path, ProviderCatalog)
    keyed = {name: spec for name, spec in catalog.providers.items() if os.environ.get(f"VERIFY_{name.upper()}_KEY")}
    if not keyed:
        print("Set VERIFY_<PROVIDER>_KEY for at least one provider, e.g. VERIFY_OPENAI_KEY.")
        return 2
    failed = 0
    async with httpx.AsyncClient(timeout=30) as http:
        for name, spec in keyed.items():
            problems = await verify(name, spec, os.environ[f"VERIFY_{name.upper()}_KEY"], http, settings)
            failed += bool(problems)
            print(f"{name}: {'OK' if not problems else ''}")
            for problem in problems:
                print(f"  - {problem}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
