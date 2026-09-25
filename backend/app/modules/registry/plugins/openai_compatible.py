"""
OpenAI-compatible listing client (`GET {base_url}/models` with a Bearer key).

Serves OpenAI, Groq, Mistral, Together, OpenRouter and any other provider that follows
the OpenAI listing shape. Differences between them (where the list sits in the response,
which fields carry context window or price, how to tell chat models apart) are declared
in the provider's `listing` block in `providers.yaml` and applied by the pure
`raw_model_from_listing`, so this client has no provider-specific code.
"""

from app.modules.registry.domain import dig, raw_model_from_listing
from app.modules.registry.plugins.base import PROVIDER_CLIENTS, BaseProviderClient
from app.modules.registry.schemas import RawModel


@PROVIDER_CLIENTS.register("openai_compatible")
class OpenAICompatibleClient(BaseProviderClient):
    client_name = "openai_compatible"

    async def list_models(self, api_key: str | None, base_url: str) -> list[RawModel]:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        payload = await self.http.get_json(f"{base_url.rstrip('/')}/models", headers)
        items = dig(payload, self.spec.listing.items_path) if self.spec.listing.items_path else payload
        rows = items if isinstance(items, list) else []
        return [raw_model_from_listing(item, self.spec.listing) for item in rows if isinstance(item, dict)]
