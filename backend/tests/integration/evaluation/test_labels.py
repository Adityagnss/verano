"""
People's labels and the evidence behind a score (ADR 0017): a label sits beside the scores and never changes one, the
majority and the split are shown, blind review leaves the judge out of the response itself, the judge's agreement
with people is measured on the labelled answers, and every score can explain itself and its limits.
"""

from typing import Any

import httpx
import pytest

from app.core.jobs import InlineJobQueue
from tests.helpers import Session, base, judged_project, run_good

pytestmark = [pytest.mark.integration]


async def judged_run(client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue) -> dict[str, Any]:
    models = await judged_project(client, session, jobs, set_judge="scripted")
    return await run_good(client, session, jobs, models)


def path(session: Session, experiment: dict[str, Any], tail: str) -> str:
    return f"{base(session)}/experiments/{experiment['id']}{tail}"


async def answers(client: httpx.AsyncClient, session: Session, experiment: dict[str, Any], **query: Any) -> list[Any]:
    cases = (await client.get(path(session, experiment, "/cases"), params=query, headers=session.headers)).json()
    return [output for case in cases for output in case["outputs"]]


async def test_a_label_is_kept_beside_the_scores_and_shows_in_the_majority_and_the_export(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    experiment = await judged_run(client, session, jobs)
    before = await answers(client, session, experiment)
    target = before[0]["test_case_run_id"]
    label = f"/answers/{target}/label"

    put = await client.put(
        path(session, experiment, label), json={"verdict": "good", "note": "right"}, headers=session.headers
    )
    assert put.status_code == 200
    assert put.json()["verdict"] == "good"
    changed = await client.put(path(session, experiment, label), json={"verdict": "bad"}, headers=session.headers)
    assert changed.json()["verdict"] == "bad"  # the same person's second label replaces the first

    after = await answers(client, session, experiment)
    first = next(o for o in after if o["test_case_run_id"] == target)
    assert first["labels"]["mine"] == "bad"
    assert first["labels"]["verdict"] == "bad"
    assert [(o["passed"], o["quality"]) for o in before] == [
        (o["passed"], o["quality"]) for o in after
    ]  # scores untouched
    csv_text = (await client.get(path(session, experiment, "/export.csv"), headers=session.headers)).text
    assert "human_label" in csv_text.splitlines()[0]
    assert ",bad," in csv_text

    gone = await client.delete(path(session, experiment, label), headers=session.headers)
    assert gone.status_code == 204
    assert (await answers(client, session, experiment))[0]["labels"] is None


async def test_blind_review_leaves_every_judge_field_out_of_the_response(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    experiment = await judged_run(client, session, jobs)
    blind = await answers(client, session, experiment, blind=True)
    assert blind
    assert all(o["hidden"] and o["scores"] == [] and not o["judged"] for o in blind)
    normal = await answers(client, session, experiment)
    assert all(o["scores"] for o in normal)


async def test_a_label_on_an_unknown_answer_is_refused(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    experiment = await judged_run(client, session, jobs)
    missing = "00000000-0000-7000-8000-000000000000"
    refused = await client.put(
        path(session, experiment, f"/answers/{missing}/label"), json={"verdict": "good"}, headers=session.headers
    )
    assert refused.status_code == 404


async def test_the_judge_is_compared_with_the_people_who_labelled_and_too_few_labels_say_so(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    experiment = await judged_run(client, session, jobs)
    assert (await client.get(path(session, experiment, "/agreement"), headers=session.headers)).json() == []
    for output in (await answers(client, session, experiment))[:4]:
        verdict = "good" if output["passed"] else "bad"  # people agree with the judge here
        await client.put(
            path(session, experiment, f"/answers/{output['test_case_run_id']}/label"),
            json={"verdict": verdict},
            headers=session.headers,
        )
    found = (await client.get(path(session, experiment, "/agreement"), headers=session.headers)).json()
    judged = next(row for row in found if row["evaluator_name"] == "g_eval_correctness")
    assert judged["answers_used"] == 4
    assert judged["raw"] == 1.0
    assert judged["too_few"]
    assert not judged["warn"]
    assert "at least 20" in judged["message"]
    assert all(row["evaluator_name"] != "exact_match" for row in found)  # only judges are compared with people


async def test_why_this_score_gives_the_reason_the_basis_and_what_the_check_cannot_tell(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    experiment = await judged_run(client, session, jobs)
    target = (await answers(client, session, experiment))[0]["test_case_run_id"]
    evidence = (
        await client.get(path(session, experiment, f"/answers/{target}/evidence"), headers=session.headers)
    ).json()
    by_name = {s["evaluator_name"]: s for s in evidence["scores"]}
    assert by_name["exact_match"]["kind"] == "rule"
    assert "cannot read meaning" in by_name["exact_match"]["limits"]
    judge = by_name["g_eval_correctness"]
    assert judge["kind"] == "judge"
    assert judge["answers_scored"] >= 1
    assert judge["reason"]
    assert judge["agreement"] is None
    assert "not yet measured" in judge["agreement_note"]


async def test_the_judge_gallery_lists_eight_judges_and_says_their_agreement_is_not_measured(
    client: httpx.AsyncClient, session: Session
) -> None:
    gallery = (await client.get(f"{base(session)}/judge-gallery", headers=session.headers)).json()
    assert {j["id"] for j in gallery} == {
        "hallucination",
        "answer_relevancy",
        "faithfulness",
        "tone",
        "pii",
        "toxicity",
        "completeness",
        "tool_use",
    }
    assert all(j["agreement"] is None and j["config"]["kind"] == "deepeval" and j["limits"] for j in gallery)
    assert next(j for j in gallery if j["id"] == "faithfulness")["config"]["requires"] == "context"
