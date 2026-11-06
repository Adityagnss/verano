"""
Drives the whole prompt-improvement loop through the HTTP API the way a person does, and prints the score of each
round, so "does Improve really lift a weak prompt in a few rounds?" is answered by a run, not a unit test.

    OPENAI_API_KEY=... uv run python scripts/flow_check.py --base http://localhost:8080 --model gpt-4o-mini

Steps: sign up a throwaway account, add the key, save a deliberately weak prompt for a ticket-sorting task, have
Verano write 50 test cases, approve them, run the prompt, then up to --rounds times: Improve, accept the best
candidate if it is proven better (or save the best one anyway with --force-save), run it, print the new score.
The key is read from the environment and never printed. Costs a few cents with a small model.
The same `run_flow` is exercised against the mock provider in tests/integration/test_flow_check.py.
"""

import argparse
import asyncio
import os
import secrets
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

WEAK_PROMPT = "Look at the support ticket and say what it is about."
SPEC = {
    "task_type": "classification",
    "goal": "Sort a customer support ticket into exactly one of the allowed labels",
    "output_format": "single_label",
    "allowed_outputs": ["billing", "shipping", "technical", "account", "other"],
    "constraints": ["Reply with the label only, in lowercase, nothing else"],
}


@dataclass
class Round:
    label: str
    pass_rate: float | None
    quality: float | None
    note: str = ""


@dataclass
class Flow:
    rounds: list[Round] = field(default_factory=list)


async def until(check: Callable[[], Awaitable[Any]], seconds: float, what: str, every: float = 2.0) -> Any:
    """Polls `check` until it returns something truthy; a stuck step ends with a message instead of hanging."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        found = await check()
        if found:
            return found
        await asyncio.sleep(every)
    raise TimeoutError(f"Still waiting for {what} after {int(seconds)} s.")


async def run_flow(
    client: httpx.AsyncClient,
    *,
    provider: str,
    api_key: str | None,
    model: str,
    writer_model: str | None = None,
    cases: int = 50,
    rounds: int = 3,
    force_save: bool = False,
    say: Callable[[str], None] = print,
    wait: float = 900.0,
    every: float = 2.0,
) -> Flow:
    email = f"flow-{secrets.token_hex(4)}@example.com"
    signed = await client.post(
        "/api/v1/auth/signup", json={"email": email, "password": secrets.token_urlsafe(16), "name": "Flow"}
    )
    signed.raise_for_status()
    headers = {"Authorization": f"Bearer {signed.json()['access_token']}"}

    async def call(method: str, path: str, **kw: Any) -> Any:
        response = await client.request(method, path, headers=headers, **kw)
        if response.status_code >= 400:
            raise RuntimeError(f"{method} {path} -> {response.status_code}: {response.text[:300]}")
        return response.json() if response.content else None

    project = await call("POST", "/api/v1/projects", json={"name": "Flow check"})
    base = f"/api/v1/projects/{project['id']}"
    credential = await call(
        "POST", f"{base}/credentials", json={"provider": provider, **({"api_key": api_key} if api_key else {})}
    )
    models = await call("GET", f"{base}/models", params={"limit": 500})
    by_name = {m["model_name"]: m for m in models["items"]}
    if model not in by_name:
        raise RuntimeError(f"The key does not reach the model {model!r}. It reaches: {sorted(by_name)[:15]}")
    writer = writer_model or model
    say(f"Account and key ready. Testing {model}, writing improvements with {writer}.")

    prompt = await call(
        "POST",
        f"{base}/prompts",
        json={"name": "Ticket sorter", "system_template": WEAK_PROMPT, "user_template": "Ticket: {{ ticket }}"},
    )
    version = prompt["latest_version"]
    say(f"Prompt v1: {WEAK_PROMPT!r}")
    generator = {"credential_id": credential["id"], "model": writer}
    spec = await call(
        "PUT", f"{base}/prompt-versions/{version['id']}/task-spec", json={"spec": SPEC, "judge": generator}
    )
    spec = await call("PUT", f"{base}/task-specs/{spec['id']}", json={"spec": spec["spec"]})
    started = await call(
        "POST", f"{base}/generations", json={"task_spec_id": spec["id"], "target_size": cases, "accept_cost": True}
    )
    dataset_id = started["id"]

    async def generated() -> bool:
        state = (await call("GET", f"{base}/dataset-versions/{dataset_id}"))["generation"] or {}
        if state.get("status") == "failed":
            raise RuntimeError(f"Writing test cases failed: {state.get('message')}")
        return state.get("status") == "succeeded"

    await until(generated, wait, "the test cases to be written", every)
    dataset = await call("GET", f"{base}/dataset-versions/{dataset_id}")
    note = (dataset["generation"] or {}).get("message") or ""
    say(f"{dataset['item_count']} test cases written ({dataset['by_split']}). {note}")
    await call("POST", f"{base}/dataset-versions/{dataset_id}/approve-drafts", json={})  # review: accept them all
    await call("POST", f"{base}/dataset-versions/{dataset_id}/approve")

    flow = Flow()
    run_body = {"models": [{"model_profile_id": by_name[model]["id"], "runs": 1, "params": {"temperature": 0}}]}

    async def run_and_score(
        label: str, prompt_version_id: str | None = None, experiment: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if experiment is None:
            body = {**run_body, **({"prompt_version_id": prompt_version_id} if prompt_version_id else {})}
            experiment = await call("POST", f"{base}/experiments", json=body)

        async def done() -> dict[str, Any] | None:
            row = await call("GET", f"{base}/experiments/{experiment['id']}")
            if row["status"] in ("failed", "cancelled"):
                raise RuntimeError(f"{label}: the run {row['status']}: {row.get('stop_reason')}")
            return row if row["status"] == "completed" else None

        await until(done, wait, f"{label} to finish", every)
        results = await call("GET", f"{base}/experiments/{experiment['id']}/results")
        (metrics,) = results["models"]
        flow.rounds.append(Round(label, metrics["pass_rate"], metrics["quality"]))
        say(f"{label}: {_pct(metrics['pass_rate'])} of answers pass (quality {_pct(metrics['quality'])}).")
        return experiment

    experiment = await run_and_score("Round 0 (the weak prompt)")
    for number in range(1, rounds + 1):
        if (flow.rounds[-1].pass_rate or 0) >= 0.9:
            say("Reached 90%: stopping.")
            break
        body = {"experiment_id": experiment["id"], "writer": generator}
        await call("POST", f"{base}/improvements", json=body)

        async def improved(baseline_id: str = experiment["id"]) -> dict[str, Any] | None:
            session = await call("GET", f"{base}/improvements/latest", params={"experiment_id": baseline_id})
            if session["stage"] in ("failed", "stopped"):
                raise RuntimeError(f"Improve {session['stage']}: {session['message']}")
            return session if session["stage"] == "done" else None

        session = await until(improved, wait, "Improve to finish", every)
        candidates = session["candidates"]
        say(
            f"Improve wrote {len(candidates)} candidates: "
            + "; ".join(f"{c['strategy']} ({_pct(c['optimize_quality'])})" for c in candidates)
        )
        say(f"Verdict: {session['message']}")
        better = next((c for c in candidates if c["outcome"] == "better"), None)
        chosen = better or (max(candidates, key=lambda c: c["optimize_quality"] or 0) if force_save else None)
        if chosen is None:
            flow.rounds.append(Round(f"Round {number}", None, None, "Improve found nothing proven better"))
            say("Nothing proven better, and --force-save is off: stopping.")
            break
        action = "accept" if better else "save"
        saved = await call(
            "POST", f"{base}/improvements/{session['id']}/candidates/{chosen['id']}/{action}", params={"run": "true"}
        )
        experiment = await call("GET", f"{base}/experiments/{saved['started_experiment_id']}")
        await run_and_score(f"Round {number} ({chosen['strategy']})", experiment=experiment)
    return flow


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{round(value * 100)}%"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", default="http://localhost:8080")
    parser.add_argument("--provider", default="openai")
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--writer", default=None, help="model that writes improvements (default: the tested model)")
    parser.add_argument("--cases", type=int, default=50)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--force-save", action="store_true", help="save the best candidate even if not proven better")
    args = parser.parse_args()
    key = os.environ.get("OPENAI_API_KEY") if args.provider == "openai" else None
    if args.provider == "openai" and not key:
        print("Set OPENAI_API_KEY in the environment (it is never printed or stored by this script).")
        return 2
    async with httpx.AsyncClient(base_url=args.base, timeout=60) as client:
        flow = await run_flow(
            client,
            provider=args.provider,
            api_key=key,
            model=args.model,
            writer_model=args.writer,
            cases=args.cases,
            rounds=args.rounds,
            force_save=args.force_save,
        )
    print("\nScores by round:")
    for r in flow.rounds:
        print(f"  {r.label}: pass {_pct(r.pass_rate)}  quality {_pct(r.quality)} {r.note}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
