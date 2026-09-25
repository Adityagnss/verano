"""
Google Gemini listing client (`GET /v1beta/models`, `x-goog-api-key` header).

Follows `nextPageToken` pagination. A model is chat-capable when its
`supportedGenerationMethods` include `generateContent`. Gemini reports token limits and
the temperature ceiling directly, which become profile values. An invalid key comes back
as HTTP 400 with reason `API_KEY_INVALID`; the provider spec lists that marker so it is
reported as an auth error like every other provider's 401.
"""

from typing import Any

from app.modules.registry.plugins.base import PROVIDER_CLIENTS, BaseProviderClient
from app.modules.registry.schemas import Capability, ParameterRange, RawModel

PAGE_SIZE = 1000
CHAT_METHOD = "generateContent"
NAME_PREFIX = "models/"


def _raw_model(item: dict[str, Any]) -> RawModel:
    chat = CHAT_METHOD in item.get("supportedGenerationMethods", [])
    ranges = {"temperature": ParameterRange(max=item["maxTemperature"])} if "maxTemperature" in item else {}
    return RawModel(
        id=str(item["name"]).removeprefix(NAME_PREFIX),
        display_name=item.get("displayName"),
        context_window=item.get("inputTokenLimit"),
        max_output_tokens=item.get("outputTokenLimit"),
        capabilities={Capability.CHAT if chat else Capability.OTHER},
        parameter_ranges=ranges,
    )


@PROVIDER_CLIENTS.register("gemini")
class GeminiClient(BaseProviderClient):
    client_name = "gemini"

    async def list_models(self, api_key: str | None, base_url: str) -> list[RawModel]:
        headers = {"x-goog-api-key": api_key or ""}
        models: list[RawModel] = []
        params: dict[str, Any] = {"pageSize": PAGE_SIZE}
        while True:
            page = await self.http.get_json(f"{base_url.rstrip('/')}/models", headers, params)
            models.extend(_raw_model(item) for item in page.get("models", []))
            if not page.get("nextPageToken"):
                return models
            params = {"pageSize": PAGE_SIZE, "pageToken": page["nextPageToken"]}
