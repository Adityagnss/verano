"""Guards against LiteLLM loading a local .env or downloading its price list at import."""

import os

import litellm
import pytest

pytestmark = pytest.mark.unit

COMPOSE_ONLY_VARIABLE = "VERANO_SITE_ADDRESS"


def test_litellm_neither_loads_a_dotenv_file_nor_fetches_remote_prices() -> None:
    assert os.environ["LITELLM_MODE"] == "PRODUCTION"
    assert os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] == "True"
    assert COMPOSE_ONLY_VARIABLE not in os.environ
    assert litellm.model_cost
