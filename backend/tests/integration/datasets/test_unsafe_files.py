"""
Integration test for untrusted uploads: an XML entity bomb and a zip bomb inside an XLSX,
a zip bomb inside a DOCX, and a PDF over the page limit each end as a failed file with a
clear message, instead of exhausting memory or time.
"""

from collections.abc import Callable

import httpx
import pytest

from app.core.jobs import InlineJobQueue
from tests.files import docx_zip_bomb, pdf_file, xlsx_with_xml_bomb, xlsx_zip_bomb
from tests.helpers import Session, get_file, upload

pytestmark = [pytest.mark.integration, pytest.mark.datasets]

UNSAFE: list[tuple[str, str, Callable[[], bytes]]] = [
    ("entity-bomb.xlsx", "golden", xlsx_with_xml_bomb),
    ("zip-bomb.xlsx", "golden", xlsx_zip_bomb),
    ("zip-bomb.docx", "document", docx_zip_bomb),
    ("too-many-pages.pdf", "document", lambda: pdf_file(["page"] * 501)),
]


@pytest.mark.parametrize(("name", "purpose", "build"), UNSAFE, ids=[u[0] for u in UNSAFE])
async def test_an_unsafe_file_fails_with_a_clear_message(
    client: httpx.AsyncClient,
    session: Session,
    jobs: InlineJobQueue,
    name: str,
    purpose: str,
    build: Callable[[], bytes],
) -> None:
    response = await upload(client, session, name, build(), purpose=purpose)
    if response.status_code != 201:
        assert response.status_code in (413, 422), response.text
        return
    await jobs.drain()
    file = await get_file(client, session, response.json()["id"])
    assert file["status"] == "failed"
    assert file["error_message"]
