"""
Anthropic listing client (`GET /v1/models`, `x-api-key` + `anthropic-version` headers).

The endpoint is paginated with `has_more` / `last_id`; all pages are followed. Anthropic
lists only chat models, so every entry is marked chat-capable. Context windows and prices
come from LiteLLM metadata and overrides during profile building.
"""

from typing import Any

from app.modules.registry.plugins.base import PROVIDER_CLIENTS, BaseProviderClient
from app.modules.registry.schemas import Capability, RawModel

PAGE_SIZE = 1000


@PROVIDER_CLIENTS.register("anthropic")
class AnthropicClient(BaseProviderClient):
    client_name = "anthropic"

    async def list_models(self, api_key: str | None, base_url: str) -> list[RawModel]:
        headers = {"x-api-key": api_key or "", "anthropic-version": self.spec.api_version or ""}
        models: list[RawModel] = []
        params: dict[str, Any] = {"limit": PAGE_SIZE}
        while True:
            page = await self.http.get_json(f"{base_url.rstrip('/')}/v1/models", headers, params)
            models.extend(
                RawModel(id=item["id"], display_name=item.get("display_name"), capabilities={Capability.CHAT})
                for item in page.get("data", [])
            )
            if not page.get("has_more") or not page.get("last_id"):
                return models
            params = {"limit": PAGE_SIZE, "after_id": page["last_id"]}
