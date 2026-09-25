"""
Mock provider listing client.

Lists the fake models defined in the gateway's `mock_models.yaml` (the same file the
LiteLLM mock handler serves), including their fake prices, so cost logic is exercised with
real arithmetic. Registered only in effect when `VERANO_MOCK_PROVIDER_ENABLED` is true;
the registry service hides the provider otherwise.
"""

from app.core.config import Settings
from app.core.datafiles import load_yaml
from app.modules.gateway.schemas import MockModelsConfig
from app.modules.registry.plugins.base import PROVIDER_CLIENTS, BaseProviderClient
from app.modules.registry.schemas import Capability, RawModel


@PROVIDER_CLIENTS.register("mock")
class MockClient(BaseProviderClient):
    client_name = "mock"

    async def list_models(self, api_key: str | None, base_url: str) -> list[RawModel]:
        settings: Settings = self.context["settings"]
        config = load_yaml(settings.mock_models_path, MockModelsConfig)
        return [
            RawModel(
                id=name,
                display_name=spec.display_name or name,
                context_window=spec.context_window,
                max_output_tokens=spec.max_output_tokens,
                input_price_per_mtok=spec.input_price_per_mtok,
                output_price_per_mtok=spec.output_price_per_mtok,
                capabilities={Capability.CHAT},
                supported_parameters=spec.supported_parameters,
            )
            for name, spec in config.models.items()
        ]
