"""
Integration tests for prompt labels (S8.1): set, move, remove, history, rollback, Accept moving a label only when
asked, and the fetch-by-name route apps call (ETag, 304, the read budget).
"""

import time
import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy import update

from app.core.container import Container
from app.core.jobs import InlineJobQueue
from app.modules.assistant.models import PromptCandidate
from app.modules.assistant.schemas import CandidateOutcome
from app.modules.prompts.models import PromptVersion
from tests.helpers import Session, approved_project, base

pytestmark = [pytest.mark.integration, pytest.mark.prompts]

READ_BUDGET_MS = 10.0


async def make_prompt(client: httpx.AsyncClient, session: Session, versions: int = 2) -> tuple[str, list[str]]:
    created = await client.post(
        f"{base(session)}/prompts",
        json={"name": "Triage", "user_template": "Ticket v1: {{ ticket }}"},
        headers=session.headers,
    )
    assert created.status_code == 201, created.text
    prompt_id = created.json()["id"]
    ids = [created.json()["latest_version"]["id"]]
    for number in range(2, versions + 1):
        saved = await client.post(
            f"{base(session)}/prompts/{prompt_id}/versions",
            json={"user_template": f"Ticket v{number}: {{{{ ticket }}}}"},
            headers=session.headers,
        )
        ids.append(saved.json()["id"])
    return prompt_id, ids


def label_url(session: Session, prompt_id: str, name: str = "production") -> str:
    return f"{base(session)}/prompts/{prompt_id}/labels/{name}"


async def put_label(
    client: httpx.AsyncClient, session: Session, prompt_id: str, version_id: str, name: str = "production"
) -> httpx.Response:
    return await client.put(
        label_url(session, prompt_id, name), json={"version_id": version_id}, headers=session.headers
    )


async def history_of(client: httpx.AsyncClient, session: Session, prompt_id: str) -> list[dict[str, Any]]:
    response = await client.get(f"{base(session)}/prompts/{prompt_id}/label-history", headers=session.headers)
    items: list[dict[str, Any]] = response.json()["items"]
    return items


async def test_a_label_is_set_moved_listed_and_removed_with_its_history(
    client: httpx.AsyncClient, session: Session
) -> None:
    prompt_id, (v1, v2) = await make_prompt(client, session)
    first = await put_label(client, session, prompt_id, v1)
    assert first.status_code == 200, first.text
    assert (first.json()["name"], first.json()["version"], first.json()["can_roll_back"]) == ("production", 1, False)
    assert (await put_label(client, session, prompt_id, v1)).status_code == 200  # same version: no new history row
    moved = await put_label(client, session, prompt_id, v2)
    assert (moved.json()["version"], moved.json()["can_roll_back"]) == (2, True)

    listed = (await client.get(f"{base(session)}/prompts/{prompt_id}/labels", headers=session.headers)).json()
    assert [(item["name"], item["version"]) for item in listed["labels"]] == [("production", 2)]
    assert listed["accept_moves_label"] is None

    rows = {(r["reason"], r["from_version"], r["to_version"]) for r in await history_of(client, session, prompt_id)}
    assert rows == {("assign", None, 1), ("assign", 1, 2)}
    only = await client.get(
        f"{base(session)}/prompts/{prompt_id}/label-history", params={"label": "staging"}, headers=session.headers
    )
    assert only.json()["items"] == []

    assert (await client.delete(label_url(session, prompt_id), headers=session.headers)).status_code == 204
    gone = await client.delete(label_url(session, prompt_id), headers=session.headers)
    assert gone.status_code == 404
    assert "isn't set" in gone.text
    rows = {(r["reason"], r["from_version"], r["to_version"]) for r in await history_of(client, session, prompt_id)}
    assert ("remove", 2, None) in rows


async def test_rollback_points_the_label_back_and_refuses_when_there_is_nowhere_to_go(
    client: httpx.AsyncClient, session: Session
) -> None:
    prompt_id, (v1, v2) = await make_prompt(client, session)
    await put_label(client, session, prompt_id, v1)
    nothing = await client.post(f"{label_url(session, prompt_id)}/rollback", headers=session.headers)
    assert nothing.status_code == 409
    await put_label(client, session, prompt_id, v2)
    back = await client.post(f"{label_url(session, prompt_id)}/rollback", headers=session.headers)
    assert back.status_code == 200, back.text
    assert back.json()["version"] == 1
    assert "rollback" in {row["reason"] for row in await history_of(client, session, prompt_id)}
    missing = await client.post(f"{label_url(session, prompt_id, 'nope')}/rollback", headers=session.headers)
    assert missing.status_code == 404


async def test_label_names_candidates_unknown_versions_and_the_limit_are_refused(
    client: httpx.AsyncClient, session: Session, container: Container, monkeypatch: pytest.MonkeyPatch
) -> None:
    prompt_id, (v1, v2) = await make_prompt(client, session)
    bad = await client.put(label_url(session, prompt_id, "Bad Name!"), json={"version_id": v1}, headers=session.headers)
    assert bad.status_code == 422
    upper = await put_label(client, session, prompt_id, v1, "Staging")  # lowercased
    assert upper.json()["name"] == "staging"
    assert (await put_label(client, session, prompt_id, str(uuid.uuid4()))).status_code == 404
    async with container.database.sessions() as db:
        await db.execute(update(PromptVersion).where(PromptVersion.id == uuid.UUID(v2)).values(is_candidate=True))
        await db.commit()
    assert (await put_label(client, session, prompt_id, v2)).status_code == 422
    monkeypatch.setattr(container.settings, "prompt_labels_max", 1)
    assert (await put_label(client, session, prompt_id, v1, "canary")).status_code == 409
    assert (await put_label(client, session, str(uuid.uuid4()), v1)).status_code == 404


async def test_accept_moves_a_label_only_when_the_prompt_asks_for_it(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    models = await approved_project(client, session, jobs)
    body = {"models": [{"model_profile_id": models["echo"], "runs": 1}]}
    experiment = (await client.post(f"{base(session)}/experiments", json=body, headers=session.headers)).json()
    await jobs.drain()
    prompt = (await client.get(f"{base(session)}/prompts", headers=session.headers)).json()["items"][0]
    prompt_id, v1 = prompt["id"], prompt["latest_version"]["id"]
    await put_label(client, session, prompt_id, v1)

    async def improved() -> dict[str, Any]:
        started = await client.post(
            f"{base(session)}/improvements", json={"experiment_id": experiment["id"]}, headers=session.headers
        )
        assert started.status_code == 202, started.text
        await jobs.drain()
        latest = await client.get(
            f"{base(session)}/improvements/latest",
            params={"experiment_id": experiment["id"]},
            headers=session.headers,
        )
        result: dict[str, Any] = latest.json()
        return result

    async def accept(result: dict[str, Any]) -> dict[str, Any]:
        chosen = next(c for c in result["candidates"] if c["holdout_experiment_id"])
        async with container.database.sessions() as db:
            await db.execute(
                update(PromptCandidate)
                .where(PromptCandidate.id == uuid.UUID(chosen["id"]))
                .values(outcome=CandidateOutcome.BETTER)
            )
            await db.commit()
        done = await client.post(
            f"{base(session)}/improvements/{result['id']}/candidates/{chosen['id']}/accept", headers=session.headers
        )
        assert done.status_code == 200, done.text
        out: dict[str, Any] = done.json()
        return out

    async def production() -> int:
        listed = (await client.get(f"{base(session)}/prompts/{prompt_id}/labels", headers=session.headers)).json()
        return int(next(item["version"] for item in listed["labels"] if item["name"] == "production"))

    default_off = await accept(await improved())  # the setting is off by default
    assert default_off["moved_label"] is None
    assert await production() == 1

    turned_on = await client.put(
        f"{base(session)}/prompts/{prompt_id}/label-settings",
        json={"accept_moves_label": "production"},
        headers=session.headers,
    )
    assert turned_on.json()["accept_moves_label"] == "production"
    on = await accept(await improved())
    assert on["moved_label"] == "production"
    assert await production() == 2  # the same improved text reuses saved version 2 (no duplicate versions)
    assert "accept" in {row["reason"] for row in await history_of(client, session, prompt_id)}
    back = await client.post(f"{label_url(session, prompt_id)}/rollback", headers=session.headers)
    assert back.json()["version"] == 1

    off = await client.put(f"{base(session)}/prompts/{prompt_id}/label-settings", json={}, headers=session.headers)
    assert off.json()["accept_moves_label"] is None


async def test_fetch_by_name_serves_label_version_or_latest_with_etag_and_304(
    client: httpx.AsyncClient, session: Session
) -> None:
    prompt_id, (v1, v2) = await make_prompt(client, session)
    url = f"{base(session)}/prompt-by-name/Triage"
    plain = await client.get(url, headers=session.headers)
    assert plain.status_code == 200
    assert plain.json()["version"] == 2
    assert plain.json()["label"] is None
    assert plain.json()["variables"] == ["ticket"]
    miss = await client.get(url, params={"label": "production"}, headers=session.headers)
    assert miss.status_code == 404
    assert "production" in miss.text

    await put_label(client, session, prompt_id, v1)
    first = await client.get(url, params={"label": "production"}, headers=session.headers)
    assert first.status_code == 200
    assert first.json()["version"] == 1
    assert first.json()["user_template"] == "Ticket v1: {{ ticket }}"
    etag = first.headers["etag"]
    same = await client.get(url, params={"label": "production"}, headers={**session.headers, "If-None-Match": etag})
    assert same.status_code == 304
    assert same.content == b""
    assert same.headers["etag"] == etag

    await put_label(client, session, prompt_id, v2)
    moved = await client.get(url, params={"label": "production"}, headers={**session.headers, "If-None-Match": etag})
    assert moved.status_code == 200
    assert moved.json()["version"] == 2
    assert moved.headers["etag"] != etag

    assert (await client.get(url, params={"version": 1}, headers=session.headers)).json()["version"] == 1
    assert (await client.get(url, params={"version": 9}, headers=session.headers)).status_code == 404
    both = await client.get(url, params={"version": 1, "label": "production"}, headers=session.headers)
    assert both.status_code == 422
    assert (await client.get(f"{base(session)}/prompt-by-name/Nope", headers=session.headers)).status_code == 404


async def test_fetch_by_name_stays_inside_the_read_budget(client: httpx.AsyncClient, session: Session) -> None:
    prompt_id, (v1, _) = await make_prompt(client, session)
    await put_label(client, session, prompt_id, v1)
    url = f"{base(session)}/prompt-by-name/Triage"
    await client.get(url, params={"label": "production"}, headers=session.headers)  # warm up
    best = float("inf")
    for _ in range(15):
        began = time.perf_counter()
        response = await client.get(url, params={"label": "production"}, headers=session.headers)
        best = min(best, (time.perf_counter() - began) * 1000)
        assert response.status_code == 200
    # The whole in-process HTTP stack (auth, project check, one query); the benchmark reports the number.
    assert best < READ_BUDGET_MS, f"fetch took {best:.1f} ms at best"
