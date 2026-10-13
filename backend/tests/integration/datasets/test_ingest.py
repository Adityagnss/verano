"""
Integration tests for input files and golden sets: an input file is one test case holding
its table summary; a golden set holds expected outputs only, paired with input files.
Covers identical results across formats, row-numbered reports, pairing (by order and by
name), a row that is itself the JSON answer, Excel-style encodings, idempotent re-import,
and memory use on a 100,000-row golden set.
"""

import csv
import hashlib
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
from tests.helpers import Session, add_golden, add_input_files, get_file, import_file, map_file, upload

pytestmark = [pytest.mark.integration, pytest.mark.datasets]

TICKETS = ["My card was charged twice", "Where is my parcel?", "The app crashes on start"]
GOLDEN: list[dict[str, Any]] = [
    {"expected": "billing", "category": "billing", "tags": "refund; urgent", "customer": "Ada"},
    {"expected": "shipping", "category": "shipping", "tags": "", "customer": "Bo"},
    {"expected": "", "category": "technical", "tags": "", "customer": "Cy"},
    {"expected": "other", "category": "other", "tags": "", "customer": "Zoë"},
]
FIRST_DATA_ROW = {"csv": 2, "xlsx": 2, "json": 1, "jsonl": 1}
MAPPING = {"expected_output": "expected", "category": "category", "tags": "tags"}


async def cases(container: Container) -> list[DatasetItem]:
    async with container.database.sessions() as db:
        return list((await db.scalars(select(DatasetItem).order_by(DatasetItem.position))).all())


def answer_of(item: DatasetItem) -> tuple[Any, ...]:
    return (item.expected_output, item.rubric, item.category, item.tags, item.source)


async def test_an_input_file_is_one_test_case_holding_its_table_summary(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    raw = [{"ticket": "Refund please"}, {"ticket": "Parcel lost"}, {"ticket": "Refund please"}]
    response = await upload(client, session, "inputs.csv", rows_file(raw, "csv"), purpose="input")
    assert response.status_code == 201, response.text
    await jobs.drain()
    done = await get_file(client, session, response.json()["id"])
    assert (done["kind"], done["status"], done["imported_rows"], done["row_count"]) == ("raw_inputs", "imported", 1, 3)
    (item,) = await cases(container)
    assert (item.source, item.review_status, item.expected_output) == ("input_file", "trusted", None)
    text = item.inputs["attachment"]
    assert "ROWS: 3" in text
    assert '"column": "ticket"' in text
    assert '"distinct_count": 2' in text


async def test_a_table_can_be_uploaded_so_that_every_row_is_its_own_test_case(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    messages = [
        {"message": "Refund please", "id": "7"},
        {"message": "", "id": "8"},
        {"message": "Parcel lost", "id": "9"},
    ]
    response = await upload(client, session, "messages.csv", rows_file(messages, "csv"), purpose="input_rows")
    assert response.status_code == 201, response.text
    await jobs.drain()
    done = await get_file(client, session, response.json()["id"])
    assert (done["kind"], done["status"], done["imported_rows"], done["row_count"]) == ("raw_inputs", "imported", 2, 3)
    items = await cases(container)
    assert [item.inputs for item in items] == [
        {"attachment": "Refund please"},
        {"attachment": "Parcel lost"},
    ]  # the blank row is skipped
    assert [item.source_row for item in items] == [2, 4]  # file row numbers, so a case can be found in the file
    assert {(item.source, item.review_status) for item in items} == {("input_file", "trusted")}

    # a table with no message column sends every filled column of the row
    table = [{"name": "Ada", "issue": "charged twice"}, {"name": "Bo", "issue": ""}]
    again = await upload(client, session, "orders.csv", rows_file(table, "csv"), purpose="input_rows")
    await jobs.drain()
    assert (await get_file(client, session, again.json()["id"]))["imported_rows"] == 2
    assert [item.inputs["attachment"] for item in (await cases(container))[2:]] == [
        "name: Ada\nissue: charged twice",
        "name: Bo",
    ]


async def test_a_table_with_nothing_in_its_rows_fails_with_a_clear_message(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    response = await upload(client, session, "empty.csv", rows_file([{"message": ""}], "csv"), purpose="input_rows")
    await jobs.drain()
    done = await get_file(client, session, response.json()["id"])
    assert done["status"] == "failed"
    assert "no test case was made" in done["error_message"]
    assert await cases(container) == []


async def test_a_golden_set_pairs_with_input_files_identically_from_every_format(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    await add_input_files(client, session, jobs, TICKETS)
    results = {}
    for file_format, first in FIRST_DATA_ROW.items():
        done = await add_golden(client, session, jobs, f"golden.{file_format}", rows_file(GOLDEN, file_format), MAPPING)
        assert (done["status"], done["kind"], done["imported_rows"]) == ("imported", "golden_set", 3), done
        report = done["validation_report"]
        assert {issue["kind"]: issue["rows"] for issue in report["issues"]} == {"missing_answer": [first + 2]}
        assert (report["valid_rows"], report["skipped_rows"]) == (3, 1)
        results[file_format] = [answer_of(item) for item in await cases(container)]
        removed = await client.delete(
            f"/api/v1/projects/{session.project_id}/input-files/{done['id']}", headers=session.headers
        )
        assert removed.status_code == 204
        assert {item.source for item in await cases(container)} == {"input_file"}  # deleting a golden set unpairs

    assert results["csv"] == results["xlsx"] == results["json"] == results["jsonl"]
    assert results["csv"][0] == ("billing", None, "billing", ["refund", "urgent"], "golden")
    assert results["csv"][2][0] == "other"
    assert [item.inputs["attachment"] for item in await cases(container)] == TICKETS


async def test_a_row_with_no_expected_output_column_is_itself_the_json_answer(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    await add_input_files(client, session, jobs, ["a table"])
    rule = [{"rule_name": "r1", "grouping_columns": ["A", "B"], "filter": {"column": "A"}}]
    done = await add_golden(client, session, jobs, "golden.json", json.dumps(rule).encode(), {})
    assert done["imported_rows"] == 1, done
    (item,) = await cases(container)
    assert json.loads(item.expected_output or "") == rule[0]
    assert item.source == "golden"


async def test_entries_pair_by_file_name_first_and_extra_entries_are_reported(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    await add_input_files(client, session, jobs, TICKETS[:2])
    rows = [
        {"expected": "second", "file": "case2.txt"},
        {"expected": "first", "file": ""},
        {"expected": "extra", "file": ""},
    ]
    done = await add_golden(
        client,
        session,
        jobs,
        "golden.csv",
        rows_file(rows, "csv"),
        {"expected_output": "expected", "input_file": "file"},
    )
    assert [item.expected_output for item in await cases(container)] == ["first", "second"]
    report = done["validation_report"]
    assert {issue["kind"]: issue["rows"] for issue in report["issues"]} == {"unpaired": [4]}
    assert (report["valid_rows"], report["skipped_rows"], done["imported_rows"]) == (2, 1, 2)


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
    await add_input_files(client, session, jobs, ["a case"])
    rows = [{"expected": "Crème brûlée was 5€ — naïve café order", "note": "x"}]
    response = await upload(client, session, "export.csv", excel_csv(rows, encoding, delimiter))
    file_id = response.json()["id"]
    await jobs.drain()
    profile = (await get_file(client, session, file_id))["profile"]
    assert profile["columns"] == ["expected", "note"]
    assert (profile["encoding"], profile["delimiter"]) == (label, delimiter)
    assert (await map_file(client, session, file_id, {"expected_output": "expected"})).status_code == 200
    await jobs.drain()
    await import_file(client, session, file_id)
    await jobs.drain()
    assert (await get_file(client, session, file_id))["validation_report"]["encoding"] == label
    (item,) = await cases(container)
    assert item.expected_output == "Crème brûlée was 5€ — naïve café order"


async def test_importing_a_golden_set_again_replaces_its_answers_instead_of_duplicating_cases(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    await add_input_files(client, session, jobs, TICKETS)
    done = await add_golden(client, session, jobs, "golden.csv", rows_file(GOLDEN, "csv"), MAPPING)
    first = [(item.id, answer_of(item)) for item in await cases(container)]
    assert (await import_file(client, session, done["id"])).status_code == 200
    await jobs.drain()
    again = [(item.id, answer_of(item)) for item in await cases(container)]
    assert again == first
    assert len(again) == 3


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
    name: str,
    content: bytes,
) -> dict[str, int]:
    file_id = (await upload(client, session, name, content)).json()["id"]
    mapping = {"expected_output": "expected"}
    stages: dict[str, Callable[[], Awaitable[Any]]] = {
        "profile": lambda: _nothing(),
        "validate": lambda: map_file(client, session, file_id, mapping),
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
    large = rows_file(large_rows(LARGE), file_format)
    path = tmp_path / f"big.{file_format}"
    path.write_bytes(large)
    loaded_row = bytes_per_row_loading_fully(path, file_format, LARGE)

    small_peaks = await stage_peaks(
        client, session, jobs, f"small.{file_format}", rows_file(large_rows(SMALL), file_format)
    )
    large_peaks = await stage_peaks(client, session, jobs, f"big.{file_format}", large)

    assert large_peaks["profile"] < small_peaks["profile"] * 1.5, (small_peaks, large_peaks)
    per_extra_row = (large_peaks["import"] - small_peaks["import"]) / (LARGE - SMALL)
    assert per_extra_row < loaded_row / 2, f"{per_extra_row:.0f} B per extra row vs {loaded_row:.0f} B per loaded row"


async def test_an_uploaded_file_reports_the_hash_of_its_content(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    content = b"first ticket text"
    response = await upload(client, session, "case.txt", content, purpose="input")
    assert response.status_code == 201, response.text
    await jobs.drain()
    done = await get_file(client, session, response.json()["id"])
    assert done["sha256"] == hashlib.sha256(content).hexdigest()
    assert done["size_bytes"] == len(content)
