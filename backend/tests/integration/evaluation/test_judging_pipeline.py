"""
What the judge sees and how checks share judge calls (ADR 0038): the prompt under test and the golden reference are
given to the judge (and each can be switched off), cache keys follow what the judge saw, fast scoring puts several
judged checks of one answer into one judge call with fallbacks, and the judge can write and self-check criteria.
"""

import copy
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from app.core.container import Container
from app.core.jobs import InlineJobQueue
from tests.helpers import Session, base, judged_project, run_good

pytestmark = [pytest.mark.integration]

STEPS = ["Compare the label with the expected label.", "Fail anything that is not one of the allowed labels."]


def judged(name: str, **config: Any) -> dict[str, Any]:
    return {
        "evaluator_name": name,
        "evaluator_version": "1",
        "config": {"kind": "deepeval", "metric": "g_eval", **config},
        "threshold": 0.5,
        "weight": 1.0,
        "required": False,
    }


TWO = [judged("tone", criteria="The answer is polite."), judged("facts", criteria="The answer is a correct label.")]


def sent(call: dict[str, Any]) -> str:
    return "\n".join(str(m["content"]) for m in call["request_messages"])


class Ctx:
    def __init__(self, client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, models: dict[str, str]):
        self.client, self.session, self.jobs, self.models = client, session, jobs, models
        self.path = ""
        self.answer = ""
        self.experiment: dict[str, Any] = {}

    async def start(self) -> "Ctx":
        self.experiment = await run_good(self.client, self.session, self.jobs, self.models)
        self.path = f"{base(self.session)}/experiments/{self.experiment['id']}"
        cases = (await self.client.get(f"{self.path}/cases", headers=self.session.headers)).json()
        self.answer = cases[0]["outputs"][0]["test_case_run_id"]
        return self

    async def rescore(self, **body: Any) -> dict[str, Any]:
        done = await self.client.post(f"{self.path}/rescore", json=body, headers=self.session.headers)
        assert done.status_code == 202, done.text
        await self.jobs.drain()
        results = (await self.client.get(f"{self.path}/results", headers=self.session.headers)).json()
        run: dict[str, Any] = results["evaluation_run"]
        return run

    async def answers(self) -> list[str]:
        cases = (await self.client.get(f"{self.path}/cases", headers=self.session.headers)).json()
        return [o["test_case_run_id"] for case in cases for o in case["outputs"]]

    async def calls(self, run_id: str) -> list[dict[str, Any]]:
        """The judge calls of one scoring pass over all answers (identical answers to the same case are judged once,
        so the call is listed under the first of them)."""
        found = []
        for answer in await self.answers():
            every = (
                await self.client.get(f"{self.path}/answers/{answer}/judge-calls", headers=self.session.headers)
            ).json()
            found += [{**c, "answer": answer} for c in every if c["evaluation_run_id"] == run_id]
        return found

    async def per_answer(self, run_id: str) -> set[int]:
        """How many judge calls each judged answer needed in one pass."""
        counts: dict[str, int] = {}
        for call in await self.calls(run_id):
            counts[call["answer"]] = counts.get(call["answer"], 0) + 1
        return set(counts.values())

    async def evidence(self) -> dict[str, dict[str, Any]]:
        body = (
            await self.client.get(f"{self.path}/answers/{self.answer}/evidence", headers=self.session.headers)
        ).json()
        return {s["evaluator_name"]: s for s in body["scores"]}


@pytest.fixture
async def ctx(client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue) -> Ctx:
    models = await judged_project(client, session, jobs, set_judge="judge")
    return await Ctx(client, session, jobs, models).start()


@pytest.fixture
async def restore(container: Container) -> AsyncIterator[None]:
    """Settings a test changes are put back, since the server settings are shared by every test."""
    settings = container.settings
    saved = settings.model_dump()
    yield
    for name in (
        "scoring_mode",
        "judge_sees_prompt",
        "judge_uses_reference",
        "fast_skip_judges_after_required_failure",
    ):
        setattr(settings, name, saved[name])


async def test_the_judge_is_given_the_prompt_and_the_reference_and_each_can_be_left_out(
    ctx: Ctx, restore: None, container: Container
) -> None:
    first = (await ctx.client.get(f"{ctx.path}/results", headers=ctx.session.headers)).json()["evaluation_run"]
    calls = await ctx.calls(first["id"])
    assert any("Classify the support ticket" in sent(c) for c in calls)
    assert any("agrees with it in substance" in sent(c) or "agree in substance" in sent(c) for c in calls)
    shown = (await ctx.evidence())["g_eval_correctness"]
    assert shown["prompt_seen"] is True
    assert shown["reference_used"] is True

    hidden = judged(
        "g_eval_correctness", criteria="The answer is a correct label.", include_prompt=False, use_reference=False
    )
    run = await ctx.rescore(evaluators=[hidden])
    after = await ctx.calls(run["id"])
    assert after
    assert not any("Classify the support ticket" in sent(c) for c in after)
    assert not any("in substance" in sent(c) for c in after)
    off = (await ctx.evidence())["g_eval_correctness"]
    assert off["prompt_seen"] is False
    assert off["reference_used"] is False

    # the server's switches do the same for every check, without editing the checks
    standard = judged("g_eval_correctness", criteria="The answer is a correct label.")
    await ctx.rescore(evaluators=[standard])
    container.settings.judge_sees_prompt = False
    container.settings.judge_uses_reference = False
    run = await ctx.rescore()
    plain = await ctx.calls(run["id"])
    assert plain
    assert not any("Classify the support ticket" in sent(c) for c in plain)
    assert not any("in substance" in sent(c) for c in plain)
    server_off = (await ctx.evidence())["g_eval_correctness"]
    assert (server_off["prompt_seen"], server_off["reference_used"]) == (False, False)


async def test_a_stored_judge_result_is_reused_only_when_the_judge_saw_the_same_things(
    ctx: Ctx, restore: None, container: Container
) -> None:
    await ctx.rescore()
    again = await ctx.rescore()
    assert await ctx.calls(again["id"]) == []  # same checks, same answers, same prompt and reference: no call
    assert (await ctx.evidence())["g_eval_correctness"]["cached"] is True

    container.settings.judge_uses_reference = False
    changed = await ctx.rescore()
    assert await ctx.calls(changed["id"])  # the judge now sees something else, so it is asked again
    assert (await ctx.evidence())["g_eval_correctness"]["cached"] is False

    container.settings.judge_sees_prompt = False
    prompt_off = await ctx.rescore()
    assert await ctx.calls(prompt_off["id"])


async def test_accurate_scoring_judges_every_check_in_its_own_calls(ctx: Ctx) -> None:
    run = await ctx.rescore(evaluators=TWO)
    calls = await ctx.calls(run["id"])
    assert await ctx.per_answer(run["id"]) == {4}  # each check: the judge writes its steps, then scores
    assert {c["evaluator"] for c in calls} == {"tone", "facts"}
    shown = await ctx.evidence()
    assert not shown["tone"]["combined"]
    assert not shown["facts"]["combined"]


async def test_fast_scoring_judges_several_checks_in_one_call_and_costs_each_its_share(
    ctx: Ctx, restore: None, container: Container
) -> None:
    container.settings.scoring_mode = "fast"
    run = await ctx.rescore(evaluators=TWO)
    calls = await ctx.calls(run["id"])
    assert await ctx.per_answer(run["id"]) == {1}
    assert "tone" in sent(calls[0])
    assert "facts" in sent(calls[0])
    shown = await ctx.evidence()
    for name in ("tone", "facts"):
        assert shown[name]["combined"] is True
        assert shown[name]["cached"] is False
        assert shown[name]["usage"]["checks_in_call"] == 2
        assert shown[name]["usage"]["input_tokens"] > 0
    results = (await ctx.client.get(f"{ctx.path}/cases", headers=ctx.session.headers)).json()
    scored = [o for case in results for o in case["outputs"] if o["judged"]]
    assert scored
    assert all(o["quality"] in (0.9, 0.3) for o in scored)

    # a second pass finds each check's stored result: no judge call at all
    again = await ctx.rescore()
    assert await ctx.calls(again["id"]) == []
    cached = await ctx.evidence()
    assert cached["tone"]["cached"] is True
    assert cached["tone"]["combined"] is True

    # one new check beside two stored ones is not worth a combined call: it is judged alone
    third = judged("clarity", criteria="The answer is clear.")
    more = await ctx.rescore(evaluators=[*TWO, third])
    assert {c["evaluator"] for c in await ctx.calls(more["id"])} == {"clarity"}


async def test_the_cost_preview_counts_one_call_per_answer_in_fast_mode_and_all_calls_otherwise(
    ctx: Ctx, restore: None, container: Container
) -> None:
    body = {"evaluators": TWO}
    url = f"{ctx.path}/rescore/estimate"
    accurate = (await ctx.client.post(url, json=body, headers=ctx.session.headers)).json()
    container.settings.scoring_mode = "fast"
    fast = (await ctx.client.post(url, json=body, headers=ctx.session.headers)).json()
    assert accurate["judge_calls"] == 6 * 4  # six answers, two checks of two calls each
    assert fast["judge_calls"] == 6  # one combined call per answer
    assert 0 < float(fast["judge_cost"]) < float(accurate["judge_cost"])
    one = (await ctx.client.post(url, json={"evaluators": TWO[:1]}, headers=ctx.session.headers)).json()
    assert one["judge_calls"] == 6 * 2  # a single check is never combined

    plan = (
        await ctx.client.post(
            f"{base(ctx.session)}/experiments/estimate",
            json={"models": [{"model_profile_id": ctx.models["good"], "runs": 1}], "evaluator_set_version_id": None},
            headers=ctx.session.headers,
        )
    ).json()
    assert plan["judge_calls"] >= 0


async def test_a_judge_that_cannot_answer_the_combined_prompt_falls_back_to_one_call_per_check(
    ctx: Ctx, restore: None, container: Container
) -> None:
    container.settings.scoring_mode = "fast"
    scripted = {"credential_id": ctx.models["_credential"], "model": "scripted"}
    run = await ctx.rescore(evaluators=TWO, judge=scripted)  # the scripted mock has no reply for the combined prompt
    shown = await ctx.evidence()
    for name in ("tone", "facts"):
        assert shown[name]["status"] == "scored"
        assert shown[name]["combined"] is False
    assert run["status"] == "completed"


async def test_fast_scoring_can_skip_the_judge_once_a_required_free_check_has_failed(
    ctx: Ctx, restore: None, container: Container
) -> None:
    container.settings.scoring_mode = "fast"
    container.settings.fast_skip_judges_after_required_failure = True
    impossible = {
        "evaluator_name": "allowed_values",
        "evaluator_version": "1",
        "config": {"kind": "rule", "allowed_outputs": ["nothing-matches"]},
        "threshold": 0.5,
        "weight": 1.0,
        "required": True,
    }
    run = await ctx.rescore(evaluators=[impossible, *TWO])
    assert await ctx.calls(run["id"]) == []
    shown = await ctx.evidence()
    for name in ("tone", "facts"):
        assert shown[name]["status"] == "unscored"
        assert "Skipped" in shown[name]["reason"]
    assert shown["allowed_values"]["passed"] is False


# -- writing criteria and the rubric self-check -------------------------------------------------------------


async def task_spec_id(client: httpx.AsyncClient, session: Session) -> tuple[str, str]:
    prompts = (await client.get(f"{base(session)}/prompts", headers=session.headers)).json()
    items = prompts["items"] if isinstance(prompts, dict) else prompts
    version = items[0]["latest_version"]["id"]
    spec = {
        "task_type": "classification",
        "goal": "Classify tickets",
        "output_format": "single_label",
        "allowed_outputs": ["billing", "shipping", "technical"],
    }
    put = await client.put(
        f"{base(session)}/prompt-versions/{version}/task-spec", json={"spec": spec}, headers=session.headers
    )
    assert put.status_code == 200, put.text
    return put.json()["id"], version


async def test_the_judge_writes_criteria_from_the_task_and_they_are_self_checked(ctx: Ctx) -> None:
    spec_id, _ = await task_spec_id(ctx.client, ctx.session)
    judge = {"credential_id": ctx.models["_credential"], "model": "judge"}
    asked = await ctx.client.post(
        f"{base(ctx.session)}/judge/criteria",
        json={"judge": judge, "task_spec_id": spec_id, "count": 4, "focus": "labels"},
        headers=ctx.session.headers,
    )
    assert asked.status_code == 200, asked.text
    body = asked.json()
    assert len(body["criteria"]) == 4
    assert "Classify tickets" in body["criteria"][0]
    assert body["review"]["judged"] is True
    assert body["review"]["ok"] is True
    assert body["evaluator_config"]["kind"] == "deepeval"
    assert all(text in body["evaluator_config"]["criteria"] for text in body["criteria"])

    unchecked = await ctx.client.post(
        f"{base(ctx.session)}/judge/criteria",
        json={"judge": judge, "task_spec_id": spec_id, "check": False},
        headers=ctx.session.headers,
    )
    assert unchecked.json()["review"] is None
    assert len(unchecked.json()["criteria"]) == 5  # the default is the middle of the allowed range

    wrong = await ctx.client.post(
        f"{base(ctx.session)}/judge/criteria",
        json={"judge": judge, "task_spec_id": "00000000-0000-0000-0000-000000000000"},
        headers=ctx.session.headers,
    )
    assert wrong.status_code == 404
    echo = {"credential_id": ctx.models["_credential"], "model": "echo"}
    unusable = await ctx.client.post(
        f"{base(ctx.session)}/judge/criteria",
        json={"judge": echo, "task_spec_id": spec_id},
        headers=ctx.session.headers,
    )
    assert unusable.status_code == 422
    assert "usable" in unusable.text


async def test_the_rubric_self_check_runs_free_checks_alone_and_a_judge_read_when_asked(ctx: Ctx) -> None:
    url = f"{base(ctx.session)}/judge/rubric-check"
    criteria = ["Be good", "Names the refund window of 30 days", "Mentions the order number of the customer", "Be good"]
    free = await ctx.client.post(url, json={"criteria": criteria}, headers=ctx.session.headers)
    assert free.status_code == 200, free.text
    body = free.json()
    assert body["judged"] is False
    assert body["ok"] is False
    assert "vague" in {i["kind"] for i in body["issues"]}
    assert {i["kind"] for i in body["issues"]} <= {"vague", "size", "duplicate"}
    assert "Run the judge check" not in body["summary"]

    clean = await ctx.client.post(
        url,
        json={
            "criteria": [
                "States the refund window of 30 days.",
                "Names the order number the customer gave.",
                "Offers one next step the customer can take.",
            ]
        },
        headers=ctx.session.headers,
    )
    assert clean.json()["ok"] is True
    assert "Run the judge check too" in clean.json()["summary"]

    judge = {"credential_id": ctx.models["_credential"], "model": "judge"}
    short = await ctx.client.post(
        url,
        json={
            "criteria": ["Offers one next step to the customer.", "Be polite", "States the refund window in days."],
            "judge": judge,
        },
        headers=ctx.session.headers,
    )
    flagged = short.json()
    assert flagged["judged"] is True
    assert flagged["ok"] is False
    assert [(i["kind"], i["criterion"]) for i in flagged["issues"] if i["criterion"] == 2]  # the mock flags short ones

    nothing = await ctx.client.post(url, json={"criteria": ["  "]}, headers=ctx.session.headers)
    assert nothing.status_code == 422
    none = await ctx.client.post(url, json={"criteria": []}, headers=ctx.session.headers)
    assert none.status_code == 422
    spec_id, version = await task_spec_id(ctx.client, ctx.session)
    with_task = await ctx.client.post(
        url,
        json={"criteria": copy.copy(criteria[:3]), "task_spec_id": spec_id, "prompt_version_id": version},
        headers=ctx.session.headers,
    )
    assert with_task.status_code == 200
    missing = await ctx.client.post(
        url,
        json={"criteria": ["x y z w v"], "prompt_version_id": "00000000-0000-0000-0000-000000000000"},
        headers=ctx.session.headers,
    )
    assert missing.status_code == 404


async def test_the_judging_tools_are_switched_off_with_their_feature(ctx: Ctx, app: Any, settings: Any) -> None:
    from app.core.config import get_settings

    app.dependency_overrides[get_settings] = lambda: settings.model_copy(
        update={"disabled_features": ["judging_tools"]}
    )
    try:
        off = await ctx.client.post(
            f"{base(ctx.session)}/judge/rubric-check", json={"criteria": ["a b c d e"]}, headers=ctx.session.headers
        )
        assert off.status_code == 409
        assert "switched off" in off.text
    finally:
        app.dependency_overrides.pop(get_settings, None)
