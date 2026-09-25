"""
Opt-in check against a real local Ollama (DEVELOPMENT.md Phase 1: one gateway call to
Ollama recorded end to end). Skipped unless VERANO_TEST_OLLAMA=1 and the model named by
VERANO_TEST_OLLAMA_MODEL (default qwen2.5:3b) has been pulled.
"""

import os
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select

from app.core.container import Container
from app.modules.gateway.models import LLMCall
from tests.helpers import Session, add_credential

pytestmark = [
    pytest.mark.integration,
    pytest.mark.gateway,
    pytest.mark.ollama,
    pytest.mark.skipif(
        os.environ.get("VERANO_TEST_OLLAMA") != "1", reason="needs a local Ollama (VERANO_TEST_OLLAMA=1)"
    ),
]

OLLAMA_URL = os.environ.get("VERANO_TEST_OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("VERANO_TEST_OLLAMA_MODEL", "qwen2.5:3b")


async def test_one_real_ollama_call_is_discovered_called_and_recorded_at_zero_cost(
    client: httpx.AsyncClient, session: Session, container: Container
) -> None:
    credential = await add_credential(client, session, "ollama", base_url=OLLAMA_URL)
    assert credential["model_count"] >= 1
    body = {
        "credential_id": credential["id"],
        "model": MODEL,
        "messages": [{"role": "user", "content": "Reply with the single word: ready"}],
        "params": {"temperature": 0, "max_tokens": 10},
    }
    response = await client.post(f"/api/v1/projects/{session.project_id}/llm-calls", json=body, headers=session.headers)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["text"].strip()
    assert Decimal(result["cost"]) == 0
    async with container.database.sessions() as db:
        call = (await db.scalars(select(LLMCall))).one()
    assert (call.status, call.model, call.params) == (
        "succeeded",
        f"ollama_chat/{MODEL}",
        {"temperature": 0, "max_tokens": 10},
    )
    assert call.input_tokens
    assert call.output_tokens
    assert call.latency_ms is not None
