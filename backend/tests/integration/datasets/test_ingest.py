"""
Integration tests for uploading rows files and turning them into test cases: identical
results across formats, row-numbered validation reports, golden vs raw inputs, Excel-style
encodings, idempotent re-import, and memory use on a 100,000-row file.
"""

import csv
import json
import tracemalloc
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from app.core.container import Container
from app.core.jobs import InlineJobQueue
from app.modules.datasets.models import DatasetItem
from tests.files import excel_csv, rows_file
from tests.helpers import Session, create_prompt, get_file, import_file, map_file, upload

pytestmark = [pytest.mark.integration, pytest.mark.datasets]

GOLDEN: list[dict[str, Any]] = [
    {
        "ticket": "My card was charged twice",
        "expected": "billing",
        "category": "billing",
        "tags": "refund; urgent",
        "customer": "Ada",
    },
    {"ticket": "Where is my parcel?", "expected": "shipping", "category": "shipping", "tags": "", "customer": "Bo"},
    {"ticket": "", "expected": "technical", "category": "technical", "tags": "", "customer": "Cy"},
    {"ticket": "The app crashes on start", "expected": "", "category": "technical", "tags": "", "customer": "Di"},
    {
        "ticket": "My card was charged twice",
        "expected": "billing",
        "category": "billing",
        "tags": "refund; urgent",
        "customer": "Ada",
    },
    {
        "ticket": "Café crème: a naïve question about €",
        "expected": "other",
        "category": "other",
        "tags": "",
        "customer": "Zoë",
    },
]
FIRST_DATA_ROW = {"csv": 2, "xlsx": 2, "json": 1, "jsonl": 1}


async def ingest(
    client: httpx.AsyncClient,
    session: Session,
    jobs: InlineJobQueue,
    name: str,
    content: bytes,
    version: dict[str, Any],
) -> dict[str, Any]:
    uploaded = await upload(client, session, name, content)
    assert uploaded.status_code == 201, uploaded.text
    file_id = uploaded.json()["id"]
    await jobs.drain()
    suggestion = await client.get(
        f"/api/v1/projects/{session.project_id}/input-files/{file_id}/mapping-suggestion",
        params={"prompt_version_id": version["id"]},
        headers=session.headers,
    )
    mapped = await map_file(client, session, file_id, version["id"], suggestion.json()["mapping"])
    assert mapped.status_code == 200, mapped.text
    await jobs.drain()
    assert (await import_file(client, session, file_id)).status_code == 200
    await jobs.drain()
    return await get_file(client, session, file_id)


async def items_of(container: Container, file_id: str) -> list[DatasetItem]:
    async with container.database.sessions() as db:
        query = select(DatasetItem).where(DatasetItem.input_file_id == file_id).order_by(DatasetItem.position)
        return list((await db.scalars(query)).all())


def content_of(item: DatasetItem) -> tuple[Any, ...]:
    return (item.inputs, item.expected_output, item.rubric, item.category, item.tags, item.extra, item.source)


async def test_a_golden_set_gives_identical_cases_from_csv_xlsx_json_and_jsonl_with_each_formats_row_numbers(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    version = await create_prompt(client, session)
    results = {}
    for file_format, first in FIRST_DATA_ROW.items():
        done = await ingest(client, session, jobs, f"golden.{file_format}", rows_file(GOLDEN, file_format), version)
        assert (done["status"], done["kind"], done["imported_rows"]) == ("imported", "golden_set", 3), done
        report = done["validation_report"]
        rows = {issue["kind"]: issue["rows"] for issue in report["issues"]}
        assert rows == {"missing_value": [first + 2], "missing_answer": [first + 3], "duplicate": [first + 4]}
        assert (report["valid_rows"], report["skipped_rows"], report["duplicates_removed"]) == (3, 2, 1)
        results[file_format] = [content_of(item) for item in await items_of(container, done["id"])]

    assert results["csv"] == results["xlsx"] == results["json"] == results["jsonl"]
    first_case = results["csv"][0]
    assert first_case[:5] == ({"ticket": "My card was charged twice"}, "billing", None, "billing", ["refund", "urgent"])
    assert first_case[5:] == ({"customer": "Ada"}, "golden")
    assert results["csv"][2][0] == {"ticket": "Café crème: a naïve question about €"}


async def test_an_input_file_is_one_test_case_holding_its_table_summary(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    raw = [{"ticket": "Refund please"}, {"ticket": "Parcel lost"}, {"ticket": "Refund please"}]
    response = await upload(client, session, "inputs.csv", rows_file(raw, "csv"), purpose="input")
    assert response.status_code == 201, response.text
    await jobs.drain()
    done = await get_file(client, session, response.json()["id"])
    assert (done["kind"], done["status"], done["imported_rows"], done["row_count"]) == ("raw_inputs", "imported", 1, 3)
    (item,) = await items_of(container, done["id"])
    assert (item.source, item.review_status, item.expected_output) == ("input_file", "trusted", None)
    text = item.inputs["attachment"]
    assert "ROWS: 3" in text
    assert '"column": "ticket"' in text
    assert '"distinct_count": 2' in text


@pytest.mark.parametrize(
    ("encoding", "delimiter", "label"),
    [("cp1252", ";", "Windows-1252"), ("utf-8-sig", ",", "UTF-8 (with BOM)"), ("utf-16", "\t", "UTF-16 (with BOM)")],
)
async def test_excel_style_csv_exports_are_decoded_and_their_encoding_is_reported(
    client: httpx.AsyncClient,
    session: Session,
    jobs: InlineJobQueue,
    container: Container,
    encoding: str,
    delimiter: str,
    label: str,
) -> None:
    version = await create_prompt(client, session)
    rows = [{"ticket": "Crème brûlée was 5€ — naïve café order", "expected": "billing"}]
    done = await ingest(client, session, jobs, "export.csv", excel_csv(rows, encoding, delimiter), version)
    assert done["profile"]["columns"] == ["ticket", "expected"]
    assert (done["profile"]["encoding"], done["profile"]["delimiter"]) == (label, delimiter)
    assert done["validation_report"]["encoding"] == label
    [item] = await items_of(container, done["id"])
    assert item.inputs == {"ticket": "Crème brûlée was 5€ — naïve café order"}


async def test_importing_a_file_again_replaces_its_cases_instead_of_duplicating_them(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    version = await create_prompt(client, session)
    done = await ingest(client, session, jobs, "golden.csv", rows_file(GOLDEN, "csv"), version)
    first = [item.id for item in await items_of(container, done["id"])]
    assert (await import_file(client, session, done["id"])).status_code == 200
    await jobs.drain()
    again = await items_of(container, done["id"])
    assert len(again) == len(first) == 3
    assert {item.id for item in again}.isdisjoint(first)


def large_rows(count: int) -> list[dict[str, Any]]:
    return [
        {"ticket": f"Ticket {n}: the order placed on day {n % 365} never arrived", "expected": "shipping"}
        for n in range(count)
    ]


def bytes_per_row_loading_fully(path: Path, file_format: str, count: int) -> float:
    tracemalloc.start()
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle)) if file_format == "csv" else json.load(handle)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    del rows
    return peak / count


async def stage_peaks(
    client: httpx.AsyncClient,
    session: Session,
    jobs: InlineJobQueue,
    version: dict[str, Any],
    name: str,
    content: bytes,
) -> dict[str, int]:
    file_id = (await upload(client, session, name, content)).json()["id"]
    mapping = {"inputs": {"ticket": "ticket"}, "expected_output": "expected"}
    stages: dict[str, Callable[[], Awaitable[Any]]] = {
        "profile": lambda: _nothing(),
        "validate": lambda: map_file(client, session, file_id, version["id"], mapping),
        "import": lambda: import_file(client, session, file_id),
    }
    peaks = {}
    for stage, start in stages.items():
        tracemalloc.start()
        await start()
        await jobs.drain()
        peaks[stage] = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
    assert (await get_file(client, session, file_id))["status"] == "imported"
    return peaks


async def _nothing() -> None:
    return None


SMALL, LARGE = 10_000, 100_000


@pytest.mark.parametrize("file_format", ["csv", "json"])
async def test_a_100k_row_file_is_streamed_and_keeps_no_row_content_in_memory(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, tmp_path: Path, file_format: str
) -> None:
    version = await create_prompt(client, session)
    large = rows_file(large_rows(LARGE), file_format)
    path = tmp_path / f"big.{file_format}"
    path.write_bytes(large)
    loaded_row = bytes_per_row_loading_fully(path, file_format, LARGE)

    small_peaks = await stage_peaks(
        client, session, jobs, version, f"small.{file_format}", rows_file(large_rows(SMALL), file_format)
    )
    large_peaks = await stage_peaks(client, session, jobs, version, f"big.{file_format}", large)

    assert large_peaks["profile"] < small_peaks["profile"] * 1.5, (small_peaks, large_peaks)
    per_extra_row = (large_peaks["import"] - small_peaks["import"]) / (LARGE - SMALL)
    assert per_extra_row < loaded_row / 2, f"{per_extra_row:.0f} B per extra row vs {loaded_row:.0f} B per loaded row"
