"""A table of inputs can fill several prompt variables: each row is a test case that carries all of them (ADR 0023)."""

import httpx
import pytest
from sqlalchemy import select

from app.core.container import Container
from app.core.jobs import InlineJobQueue
from app.modules.datasets.models import DatasetItem
from tests.files import rows_file
from tests.helpers import Session, get_file, upload

pytestmark = [pytest.mark.integration, pytest.mark.datasets]

ROWS = [
    {"Question": "How long is shipping?", "Context": "Shipping takes 3 days.", "Lang": "en", "Answer": "3 days"},
    {"Question": "Reset my password", "Context": "", "Lang": "en", "Answer": "Use the link"},
    {"Question": "Wie lange dauert der Versand?", "Context": "Versand dauert 3 Tage.", "Lang": "de", "Answer": ""},
]


def url(session: Session, file_id: str) -> str:
    return f"/api/v1/projects/{session.project_id}/input-files/{file_id}/variables"


async def items(container: Container) -> list[DatasetItem]:
    async with container.database.sessions() as db:
        return list((await db.scalars(select(DatasetItem).order_by(DatasetItem.position))).all())


async def test_columns_fill_variables_and_an_empty_cell_leaves_the_row_out_with_the_reason(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    uploaded = await upload(client, session, "cases.csv", rows_file(ROWS, "csv"), purpose="input_rows")
    await jobs.drain()
    file_id = uploaded.json()["id"]
    body = {
        "variables": {"question": "Question", "context": "Context", "language": "Lang"},
        "expected_output": "Answer",
    }
    mapped = await client.put(url(session, file_id), json=body, headers=session.headers)
    assert mapped.status_code == 200, mapped.text
    await jobs.drain()

    done = await get_file(client, session, file_id)
    assert (done["status"], done["imported_rows"]) == ("imported", 2)
    found = await items(container)
    assert [item.inputs for item in found] == [
        {"question": "How long is shipping?", "context": "Shipping takes 3 days.", "language": "en"},
        {"question": "Wie lange dauert der Versand?", "context": "Versand dauert 3 Tage.", "language": "de"},
    ]
    assert [item.expected_output for item in found] == ["3 days", None]
    assert any("Row 3" in warning and "context" in warning for warning in done["profile"]["warnings"])


async def test_a_mapping_with_a_missing_column_or_a_bad_name_is_refused_with_every_problem(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    uploaded = await upload(client, session, "cases.csv", rows_file(ROWS, "csv"), purpose="input_rows")
    await jobs.drain()
    body = {"variables": {"1st": "Question", "ctx": "Nope"}}
    refused = await client.put(url(session, uploaded.json()["id"]), json=body, headers=session.headers)
    assert refused.status_code == 422
    assert len(refused.json()["error"]["details"]["problems"]) == 2
