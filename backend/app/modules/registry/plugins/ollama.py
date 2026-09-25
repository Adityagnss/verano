"""
Ollama listing client (`GET /api/tags`, then `POST /api/show` per model; no key).

`/api/tags` lists the locally pulled models; `/api/show` adds each model's capabilities
(chat vs embedding) and context length from its `model_info`. An unreachable Ollama is
reported with the address that was tried, since the usual cause is a wrong
`OLLAMA_BASE_URL` or Ollama not running.
"""

import asyncio
from typing import Any

from app.modules.registry.plugins.base import PROVIDER_CLIENTS, BaseProviderClient
from app.modules.registry.schemas import Capability, RawModel

CAPABILITY_MAP = {"completion": Capability.CHAT, "embedding": Capability.EMBEDDING}
CONTEXT_SUFFIX = ".context_length"


def _context_length(model_info: dict[str, Any]) -> int | None:
    values = [v for k, v in model_info.items() if k.endswith(CONTEXT_SUFFIX) and isinstance(v, int)]
    return values[0] if values else None


@PROVIDER_CLIENTS.register("ollama")
class OllamaClient(BaseProviderClient):
    client_name = "ollama"

    async def list_models(self, api_key: str | None, base_url: str) -> list[RawModel]:
        root = base_url.rstrip("/")
        tags = await self.http.get_json(f"{root}/api/tags", {})
        names = [str(item["name"]) for item in tags.get("models", [])]
        details = await asyncio.gather(*(self.http.post_json(f"{root}/api/show", {}, {"model": n}) for n in names))
        return [self._raw_model(name, detail) for name, detail in zip(names, details, strict=True)]

    async def validate(self, api_key: str | None, base_url: str) -> None:
        await self.http.get_json(f"{base_url.rstrip('/')}/api/tags", {})

    @staticmethod
    def _raw_model(name: str, detail: dict[str, Any]) -> RawModel:
        capabilities = {CAPABILITY_MAP.get(c, Capability.OTHER) for c in detail.get("capabilities", ["completion"])}
        return RawModel(
            id=name,
            display_name=name,
            context_window=_context_length(detail.get("model_info", {})),
            capabilities=capabilities,
        )
