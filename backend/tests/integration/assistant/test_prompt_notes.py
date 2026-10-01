"""The Prompt guide is served to signed-in users only."""

import httpx
import pytest

from tests.helpers import Session

pytestmark = [pytest.mark.integration]


async def test_prompt_notes_are_served_to_signed_in_users_only(client: httpx.AsyncClient, session: Session) -> None:
    anonymous = await client.get("/api/v1/prompt-notes")
    assert anonymous.status_code == 401
    response = await client.get("/api/v1/prompt-notes", headers=session.headers)
    assert response.status_code == 200
    assert response.json()["markdown"].startswith("# Prompting guide")
