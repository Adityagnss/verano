"""S8.9, scoring half: checks on a stable sample of live traffic, free rule checks, a judge sample with a monthly cap,
and the daily line per prompt version."""

from typing import Any

import httpx
import pytest

from app.core.container import Container
from app.core.jobs import InlineJobQueue
from app.modules.traffic.domain import in_sample
from tests import traffic_samples as samples
from tests.helpers import Session, judged_project
from tests.traffic_support import import_data, set_config, stats, tbase, trace_rows, traces

pytestmark = [pytest.mark.integration]


def calls(count: int, answer: str = "billing", start: int = 1, version: str | None = None) -> list[dict[str, Any]]:
    spans = []
    for i in range(count):
        span = samples.otel_span(start + i, f"ticket text number {start + i}", answer)
        if version:
            span["attributes"].append(samples._s("verano.prompt_version", version))
        spans.append(span)
    return spans


async def send(client: httpx.AsyncClient, session: Session, spans: list[dict[str, Any]]) -> None:
    assert (await import_data(client, session, samples.otel_export(spans))).status_code == 201


async def run_scoring(client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue) -> dict[str, Any]:
    response = await client.post(f"{tbase(session)}/scoring/run", headers=session.headers)
    assert response.status_code == 200, response.text
    await jobs.drain()
    body: dict[str, Any] = response.json()
    return body


async def test_scoring_does_nothing_until_it_is_switched_on_and_says_so(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    await send(client, session, calls(3))
    result = await run_scoring(client, session, jobs)
    assert result["queued"] is False
    assert "Turn on online scoring" in result["message"]
    assert {t["score_state"] for t in await traces(client, session)} == {"new"}


async def test_without_checks_traces_wait_marked_and_are_scored_once_checks_exist(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    await send(client, session, calls(3))
    await set_config(client, session, scoring_enabled=True, rule_sample_rate=1.0, judge_sample_rate=0.0)
    await run_scoring(client, session, jobs)
    assert {t["score_state"] for t in await traces(client, session)} == {"no_checks"}
    seen = await stats(client, session)
    assert seen["has_checks"] is False
    assert seen["by_state"] == {"no_checks": 3}
    await judged_project(client, session, jobs, set_judge="scripted")
    await run_scoring(client, session, jobs)
    assert {t["score_state"] for t in await traces(client, session)} == {"scored"}


async def test_rule_checks_score_every_sampled_trace_for_free_and_a_wrong_answer_fails(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    await judged_project(client, session, jobs, set_judge="scripted")
    await send(client, session, calls(4, "billing") + calls(2, "I have no idea what you mean", start=10))
    await set_config(client, session, scoring_enabled=True, rule_sample_rate=1.0, judge_sample_rate=0.0)
    from sqlalchemy import func, select

    from app.modules.gateway.models import LLMCall

    async with container.database.sessions() as db:
        before = int(await db.scalar(select(func.count()).select_from(LLMCall)) or 0)
    await run_scoring(client, session, jobs)
    async with container.database.sessions() as db:
        after = int(await db.scalar(select(func.count()).select_from(LLMCall)) or 0)
    assert after == before  # no model call was made: rule checks are free
    listed = await traces(client, session)
    assert {t["score_state"] for t in listed} == {"scored"}
    good = [t for t in listed if t["output_preview"] == "billing"]
    bad = [t for t in listed if t["output_preview"] != "billing"]
    assert all(t["passed"] is True and t["quality"] == 1.0 for t in good)
    assert all(t["passed"] is False for t in bad)
    detail = (await client.get(f"{tbase(session)}/{bad[0]['id']}", headers=session.headers)).json()
    assert detail["scores"]
    assert all(not s["judged"] for s in detail["scores"])
    assert any(s["passed"] is False and s["reason"] for s in detail["scores"])


async def test_a_failed_call_counts_as_a_failure_without_running_any_check(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    await judged_project(client, session, jobs, set_judge="scripted")
    await send(client, session, [samples.otel_span(1, "will fail", "partial", error=True)])
    await set_config(client, session, scoring_enabled=True, rule_sample_rate=1.0, judge_sample_rate=1.0)
    await run_scoring(client, session, jobs)
    only = (await traces(client, session))[0]
    assert only["score_state"] == "scored"
    assert only["passed"] is False
    assert only["quality"] == 0.0
    detail = (await client.get(f"{tbase(session)}/{only['id']}", headers=session.headers)).json()
    assert [s["evaluator_name"] for s in detail["scores"]] == ["call_error"]


async def test_the_sample_is_the_same_on_every_run_and_matches_the_stable_hash(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    await judged_project(client, session, jobs, set_judge="scripted")
    await send(client, session, calls(60))
    await set_config(client, session, scoring_enabled=True, rule_sample_rate=0.3, judge_sample_rate=0.0)
    await run_scoring(client, session, jobs)
    first = {t["id"]: t["score_state"] for t in await traces(client, session)}
    expected = {i: ("scored" if in_sample(i, 0.3, "rule") else "sampled_out") for i in first}
    assert first == expected
    assert 0 < sum(v == "scored" for v in first.values()) < 60
    await run_scoring(client, session, jobs)  # a second run changes nothing
    assert {t["id"]: t["score_state"] for t in await traces(client, session)} == first


async def test_raising_the_sample_rate_only_adds_traces_to_the_scored_set(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    await judged_project(client, session, jobs, set_judge="scripted")
    await send(client, session, calls(60))
    await set_config(client, session, scoring_enabled=True, rule_sample_rate=0.2, judge_sample_rate=0.0)
    await run_scoring(client, session, jobs)
    low = {t["id"] for t in await traces(client, session) if t["score_state"] == "scored"}
    await set_config(client, session, rule_sample_rate=0.6)
    # traces already looked at keep their state; new traffic follows the new rate
    await send(client, session, calls(60, start=100))
    await run_scoring(client, session, jobs)
    later = {t["id"] for t in await traces(client, session) if t["score_state"] == "scored"}
    assert low <= later
    assert len(later) > len(low)


async def test_judge_checks_run_on_a_sample_and_never_beyond_the_monthly_limit(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    await judged_project(client, session, jobs, set_judge="scripted")
    await send(client, session, calls(12))
    await set_config(
        client, session, scoring_enabled=True, rule_sample_rate=1.0, judge_sample_rate=1.0, judge_monthly_limit=3
    )
    await run_scoring(client, session, jobs)
    seen = await stats(client, session)
    assert seen["judge_used_this_month"] == 3
    assert seen["judge_monthly_limit"] == 3
    assert seen["by_state"] == {"scored": 12}  # the rest were still scored by the free rule checks
    await send(client, session, calls(5, start=50))
    await run_scoring(client, session, jobs)
    assert (await stats(client, session))["judge_used_this_month"] == 3  # the cap holds across runs
    assert sum(row.judged for row in await trace_rows(container, session)) == 3


async def test_a_zero_judge_limit_means_no_judge_calls_at_all(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    await judged_project(client, session, jobs, set_judge="scripted")
    await send(client, session, calls(5))
    await set_config(
        client, session, scoring_enabled=True, rule_sample_rate=1.0, judge_sample_rate=1.0, judge_monthly_limit=0
    )
    await run_scoring(client, session, jobs)
    assert (await stats(client, session))["judge_used_this_month"] == 0


async def test_the_daily_line_has_one_row_per_day_and_prompt_version(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    await judged_project(client, session, jobs, set_judge="scripted")
    await send(
        client, session, calls(4, "billing", start=1, version="v1") + calls(2, "nonsense words", start=20, version="v2")
    )
    await set_config(client, session, scoring_enabled=True, rule_sample_rate=1.0, judge_sample_rate=0.0)
    await run_scoring(client, session, jobs)
    line = (await client.get(f"{tbase(session)}/daily", params={"days": 30}, headers=session.headers)).json()
    by_version = {row["prompt_version"]: row for row in line}
    assert set(by_version) == {"v1", "v2"}
    assert by_version["v1"]["traces"] == 4
    assert by_version["v1"]["passed"] == 4
    assert by_version["v1"]["pass_rate"] == 1.0
    assert by_version["v2"]["traces"] == 2
    assert by_version["v2"]["pass_rate"] == 0.0
    assert by_version["v1"]["mean_quality"] == 1.0
    assert by_version["v1"]["scored"] == 4


async def test_scheduled_processing_scores_traffic_for_a_project_that_is_not_receiving_now(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    await judged_project(client, session, jobs, set_judge="scripted")
    await send(client, session, calls(3))
    await set_config(client, session, scoring_enabled=True, rule_sample_rate=1.0, judge_sample_rate=0.0)
    await container.valkey.flushall()
    container.jobs.enqueue("traffic.sweep")
    await jobs.drain()
    assert {t["score_state"] for t in await traces(client, session)} == {"scored"}
