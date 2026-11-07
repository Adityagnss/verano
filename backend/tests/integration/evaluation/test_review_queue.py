"""
Integration tests for the review queue (ADR 0038, S6.6): giving answers to people, a person's queue and progress,
blind review that leaves every judge field out of the response itself, and an owner settling disagreements.
The project's workspace is made a shared one so a second person can join it through an invite.
"""

import uuid
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import update

from app.core.config import Settings, get_settings
from app.core.container import Container
from app.core.jobs import InlineJobQueue
from app.modules.auth.models import Organization
from tests.helpers import Session, base, judged_project, run_good, sign_up

pytestmark = [pytest.mark.integration]

JUDGE_FIELDS = ("judge", "labels", "resolution")


class Team:
    def __init__(self, owner: Session, member_headers: dict[str, str], member_id: str, experiment: dict[str, Any]):
        self.owner = owner
        self.member = member_headers
        self.member_id = member_id
        self.experiment = experiment
        self.q = f"{base(owner)}/review-queue"
        self.exp = f"{base(owner)}/experiments/{experiment['id']}"


async def team(client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container) -> Team:
    models = await judged_project(client, session, jobs, set_judge="scripted")
    experiment = await run_good(client, session, jobs, models)
    project = (await client.get(base(session), headers=session.headers)).json()
    org = uuid.UUID(project["organization_id"])
    async with container.database.sessions() as db:
        await db.execute(update(Organization).where(Organization.id == org).values(is_personal=False))
        await db.commit()
    email = f"member-{uuid.uuid4().hex[:8]}@example.com"
    issued = await client.post(
        f"/api/v1/organizations/{org}/invites", json={"email": email, "role": "member"}, headers=session.headers
    )
    assert issued.status_code == 201, issued.text
    headers = await sign_up(client, email)
    token = issued.json()["link"].rsplit("/", 1)[1]
    accepted = await client.post(f"/api/v1/auth/invites/{token}/accept", headers=headers)
    assert accepted.status_code == 200, accepted.text
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    return Team(session, headers, me["user"]["id"], experiment)


async def answer_ids(client: httpx.AsyncClient, t: Team) -> list[str]:
    cases = (await client.get(f"{t.exp}/cases", headers=t.owner.headers)).json()
    return [o["test_case_run_id"] for case in cases for o in case["outputs"]]


async def label(client: httpx.AsyncClient, t: Team, headers: dict[str, str], run: str, verdict: str) -> None:
    done = await client.put(f"{t.exp}/answers/{run}/label", json={"verdict": verdict}, headers=headers)
    assert done.status_code == 200, done.text


async def assign(client: httpx.AsyncClient, t: Team, headers: dict[str, str] | None = None, **body: Any) -> Any:
    return await client.post(
        f"{t.q}/assignments",
        json={"experiment_id": t.experiment["id"], **body},
        headers=headers or t.owner.headers,
    )


async def test_members_and_assigning_to_yourself_another_member_and_a_stranger(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    t = await team(client, session, jobs, container)
    members = (await client.get(f"{t.q}/members", headers=session.headers)).json()
    assert {m["user_id"]: m["is_owner"] for m in members} == {str(session.user_id): True, t.member_id: False}

    me = await assign(client, t, count=2)
    assert me.status_code == 201
    assert me.json()["assigned"] == 2
    other = await assign(client, t, count=2, assignee_user_id=t.member_id, blind=True, batch_label="Tuesday")
    assert other.json()["assigned"] == 2

    stranger = await assign(client, t, count=1, assignee_user_id=str(uuid.uuid4()))
    assert stranger.status_code == 422  # not a member of the workspace
    assert "isn't a member" in stranger.text
    neither = await assign(client, t)
    assert neither.status_code == 422
    both = await assign(client, t, count=1, test_case_run_ids=[str(uuid.uuid4())])
    assert both.status_code == 422


async def test_explicit_answers_must_belong_to_the_experiment_repeats_are_counted_and_the_cap_holds(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    t = await team(client, session, jobs, container)
    ids = await answer_ids(client, t)
    foreign = await assign(client, t, test_case_run_ids=[ids[0], str(uuid.uuid4())])
    assert foreign.status_code == 422
    assert "don't belong" in foreign.text

    first = await assign(client, t, test_case_run_ids=ids[:3])
    assert first.json()["assigned"] == 3
    again = await assign(client, t, test_case_run_ids=ids[1:4])
    assert (again.json()["assigned"], again.json()["already_assigned"]) == (1, 2)

    await label(client, t, session.headers, ids[5], "good")
    skipped = await assign(client, t, test_case_run_ids=[ids[5]])
    assert skipped.json()["skipped"] == 1
    assert skipped.json()["assigned"] == 0

    capped = await assign(client, t, count=100000)
    assert capped.status_code == 422
    assert "At most" in capped.text
    missing = await client.post(
        f"{t.q}/assignments",
        json={"experiment_id": str(uuid.uuid4()), "count": 1},
        headers=session.headers,
    )
    assert missing.status_code == 404


async def test_count_picks_unlabelled_answers_and_says_so_when_none_are_left(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    t = await team(client, session, jobs, container)
    ids = await answer_ids(client, t)
    await label(client, t, t.member, ids[0], "good")
    picked = await assign(client, t, count=10)
    assert picked.json()["assigned"] == len(ids) - 1  # the labelled one is not given out
    queue = (await client.get(f"{t.q}/mine", headers=session.headers)).json()
    assert ids[0] not in {i["test_case_run_id"] for i in queue["items"]}
    nothing = await assign(client, t, count=10)
    assert nothing.json()["assigned"] == 0
    assert "no more answers" in nothing.json()["message"]


async def test_the_queue_follows_labelling_pages_oldest_first_and_progress_counts_everyone(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    t = await team(client, session, jobs, container)
    ids = await answer_ids(client, t)
    await assign(client, t, test_case_run_ids=ids[:4])
    await assign(client, t, test_case_run_ids=ids[:2], assignee_user_id=t.member_id)

    page = (await client.get(f"{t.q}/mine", params={"limit": 3}, headers=session.headers)).json()
    assert [i["test_case_run_id"] for i in page["items"]] == ids[:3]
    assert page["next_cursor"]
    assert page["open"] == 4
    rest = (
        await client.get(f"{t.q}/mine", params={"limit": 3, "cursor": page["next_cursor"]}, headers=session.headers)
    ).json()
    assert [i["test_case_run_id"] for i in rest["items"]] == ids[3:4]
    assert rest["next_cursor"] is None

    await label(client, t, session.headers, ids[0], "good")
    mine = (await client.get(f"{t.q}/mine", headers=session.headers)).json()
    assert (mine["open"], mine["done"]) == (3, 1)
    assert ids[0] not in {i["test_case_run_id"] for i in mine["items"]}
    done = (await client.get(f"{t.q}/mine", params={"status": "done"}, headers=session.headers)).json()
    assert [i["test_case_run_id"] for i in done["items"]] == [ids[0]]
    assert done["items"][0]["done"]
    assert done["items"][0]["my_label"] == "good"

    progress = (
        await client.get(f"{t.q}/progress", params={"experiment_id": t.experiment["id"]}, headers=session.headers)
    ).json()
    assert (progress["assigned"], progress["done"], progress["open"]) == (6, 1, 5)
    by_user = {p["user_id"]: (p["assigned"], p["done"]) for p in progress["people"]}
    assert by_user == {str(session.user_id): (4, 1), t.member_id: (2, 0)}


async def test_a_blind_review_leaves_every_judge_field_out_of_the_response(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    t = await team(client, session, jobs, container)
    ids = await answer_ids(client, t)
    await label(client, t, t.member, ids[0], "bad")
    await assign(client, t, test_case_run_ids=[ids[0], ids[1]], blind=True)
    await assign(client, t, test_case_run_ids=[ids[2]])

    items = (await client.get(f"{t.q}/mine", headers=session.headers)).json()["items"]
    by_id = {i["test_case_run_id"]: i for i in items}
    for run in (ids[0], ids[1]):  # given blind
        item = by_id[run]
        assert item["hidden"] is True
        assert item["blind"] is True
        assert all(item[field] is None for field in JUDGE_FIELDS)
    open_item = by_id[ids[2]]
    assert open_item["hidden"] is False
    assert open_item["judge"] is not None
    assert open_item["judge"]["scores"]

    forced = (await client.get(f"{t.q}/mine", params={"blind": "true"}, headers=session.headers)).json()["items"]
    assert len(forced) == 3
    for item in forced:
        assert item["hidden"] is True
        assert all(item[field] is None for field in JUDGE_FIELDS)
    raw = (await client.get(f"{t.q}/mine", params={"blind": "true"}, headers=session.headers)).text
    assert "g_eval_correctness" not in raw  # no judge name anywhere in the body


async def test_only_an_owner_settles_a_disagreement_and_nothing_else_changes(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    t = await team(client, session, jobs, container)
    ids = await answer_ids(client, t)
    target, other = ids[0], ids[1]
    await label(client, t, session.headers, target, "good")
    await label(client, t, t.member, target, "bad")
    await label(client, t, session.headers, other, "good")
    scores_before = (await client.get(f"{t.exp}/results", headers=session.headers)).json()
    url = f"{t.q}/disputes/{t.experiment['id']}/{target}/resolution"

    found = (
        await client.get(f"{t.q}/disputes", params={"experiment_id": t.experiment["id"]}, headers=session.headers)
    ).json()
    assert [d["test_case_run_id"] for d in found] == [target]
    assert {p["verdict"] for p in found[0]["labels"]} == {"good", "bad"}
    assert (
        await client.get(f"{t.q}/progress", params={"experiment_id": t.experiment["id"]}, headers=session.headers)
    ).json()["disputed"] == 1

    refused = await client.put(url, json={"verdict": "good"}, headers=t.member)
    assert refused.status_code == 403
    not_final = await client.put(url, json={"verdict": "unsure"}, headers=session.headers)
    assert not_final.status_code == 422
    not_disputed = await client.put(
        f"{t.q}/disputes/{t.experiment['id']}/{other}/resolution", json={"verdict": "good"}, headers=session.headers
    )
    assert not_disputed.status_code == 409

    settled = await client.put(url, json={"verdict": "bad", "note": "wrong label"}, headers=session.headers)
    assert settled.status_code == 200
    assert settled.json()["verdict"] == "bad"
    replaced = await client.put(url, json={"verdict": "good"}, headers=session.headers)
    assert replaced.json()["verdict"] == "good"
    assert (
        await client.get(f"{t.q}/disputes", params={"experiment_id": t.experiment["id"]}, headers=session.headers)
    ).json() == []
    with_settled = (
        await client.get(
            f"{t.q}/disputes",
            params={"experiment_id": t.experiment["id"], "include_settled": "true"},
            headers=session.headers,
        )
    ).json()
    assert with_settled[0]["resolution"]["verdict"] == "good"
    progress = (
        await client.get(f"{t.q}/progress", params={"experiment_id": t.experiment["id"]}, headers=session.headers)
    ).json()
    assert (progress["disputed"], progress["resolved"]) == (0, 1)

    # shown to a non-blind reviewer, hidden from a blind one
    await assign(client, t, test_case_run_ids=[ids[2]], assignee_user_id=t.member_id)
    await label(client, t, t.member, ids[2], "good")
    # the member's queue now holds a labelled answer; the settled one is shown to a reviewer who is not blind
    await client.delete(f"{t.exp}/answers/{target}/label", headers=t.member)
    await assign(client, t, test_case_run_ids=[target], assignee_user_id=t.member_id)
    await label(client, t, t.member, target, "bad")  # back to the same disagreement, still settled
    done = {
        i["test_case_run_id"]: i
        for i in (await client.get(f"{t.q}/mine", params={"status": "all"}, headers=t.member)).json()["items"]
    }
    assert done[target]["resolution"]["verdict"] == "good"
    blind_view = (await client.get(f"{t.q}/mine", params={"status": "all", "blind": "true"}, headers=t.member)).json()
    assert all(i["resolution"] is None for i in blind_view["items"])

    assert (await client.get(f"{t.exp}/results", headers=session.headers)).json() == scores_before
    assert (await client.delete(url, headers=t.member)).status_code == 403
    assert (await client.delete(url, headers=session.headers)).status_code == 204
    gone = (
        await client.get(f"{t.q}/disputes", params={"experiment_id": t.experiment["id"]}, headers=session.headers)
    ).json()
    assert [d["test_case_run_id"] for d in gone] == [target]


async def test_pick_disputed_gives_the_disagreements_a_person_has_not_labelled(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    t = await team(client, session, jobs, container)
    ids = await answer_ids(client, t)
    await label(client, t, session.headers, ids[0], "good")
    await label(client, t, t.member, ids[0], "bad")
    picked = await assign(client, t, count=5, pick="disputed", assignee_user_id=str(uuid.uuid4()))
    assert picked.status_code == 422
    own = await assign(client, t, count=5, pick="disputed")
    assert own.json()["assigned"] == 0  # the owner already labelled it
    third = await assign(client, t, count=5, pick="disputed", assignee_user_id=t.member_id)
    assert third.json()["assigned"] == 0


async def test_unassigning_is_for_the_assignee_or_the_giver_only(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    t = await team(client, session, jobs, container)
    ids = await answer_ids(client, t)
    await assign(client, t, test_case_run_ids=ids[:1], assignee_user_id=t.member_id)
    item = (await client.get(f"{t.q}/mine", headers=t.member)).json()["items"][0]
    url = f"{t.q}/assignments/{item['assignment_id']}"
    third = await sign_up(client, f"third-{uuid.uuid4().hex[:6]}@example.com")
    assert (await client.delete(url, headers=third)).status_code in (403, 404)
    assert (await client.delete(url, headers=session.headers)).status_code == 204  # the giver
    assert (await client.get(f"{t.q}/mine", headers=t.member)).json()["items"] == []
    assert (await client.delete(url, headers=t.member)).status_code == 404


async def test_the_queue_is_switched_off_with_its_feature(
    client: httpx.AsyncClient, session: Session, app: FastAPI, settings: Settings
) -> None:
    app.dependency_overrides[get_settings] = lambda: settings.model_copy(update={"disabled_features": ["review_queue"]})
    try:
        off = await client.get(f"{base(session)}/review-queue/members", headers=session.headers)
        assert off.status_code == 409
        assert "switched off" in off.text
    finally:
        app.dependency_overrides.pop(get_settings, None)


async def test_a_settled_disagreement_counts_in_the_judge_agreement_with_the_owners_verdict(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    t = await team(client, session, jobs, container)
    target = (await answer_ids(client, t))[0]
    await label(client, t, session.headers, target, "good")
    await label(client, t, t.member, target, "bad")

    def used(rows: list[dict[str, Any]]) -> dict[str, int]:
        return {r["evaluator_name"]: r["answers_used"] for r in rows if r["evaluator_name"] == "g_eval_correctness"}

    before = (await client.get(f"{t.exp}/agreement", headers=session.headers)).json()
    assert used(before) == {}  # a tied answer has no verdict to compare the judge with

    url = f"{t.q}/disputes/{t.experiment['id']}/{target}/resolution"
    assert (await client.put(url, json={"verdict": "good"}, headers=session.headers)).status_code == 200
    after = (await client.get(f"{t.exp}/agreement", headers=session.headers)).json()
    assert used(after) == {"g_eval_correctness": 1}
    row = next(r for r in after if r["evaluator_name"] == "g_eval_correctness")
    assert row["unsure_or_disputed"] == 0
    assert row["true_pass"] + row["false_fail"] == 1  # compared with "good"

    assert (await client.delete(url, headers=session.headers)).status_code == 204
    assert used((await client.get(f"{t.exp}/agreement", headers=session.headers)).json()) == {}
