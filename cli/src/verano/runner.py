"""
`verano run` and `verano status`.

`run` starts one experiment per prompt entry on the project's approved test cases, shows the cost
before anything is sent, waits for the answers and their scoring, prints the results and a link,
and (with `--ci`) turns the prompt's `gate:` into an exit code. Ctrl-C stops the experiment so
nothing keeps spending after you leave.
"""

import json
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import click
import typer

from verano import auth, ui
from verano.client import ApiClient
from verano.errors import CliError, GateFailed
from verano.gate import Verdict, evaluate
from verano.loader import Loaded, ResolvedPrompt, find_file, load
from verano.push import resolve_model
from verano.report import money, results_table

POLL_S = 2.0
PROGRESS_S = 10.0
TIMEOUT_S = 1800.0
DEFAULTS: dict[str, float | int] = {"temperature": 0, "seed": 42}
FINISHED = {"completed", "cancelled", "failed"}


@dataclass
class EntryResult:
    name: str
    project: str
    project_id: str | None = None
    experiment_id: str | None = None
    link: str | None = None
    status: str | None = None
    models: list[dict[str, Any]] = field(default_factory=list)
    verdict: Verdict | None = None
    error: str | None = None


def find_project(api: ApiClient, name: str) -> dict[str, Any]:
    matches = [p for p in api.pages("/projects") if p["name"] == name]
    if not matches:
        raise CliError(f'There is no project "{name}" yet.', "Run `verano push` first.")
    if len(matches) > 1:
        raise CliError(
            f'{len(matches)} projects are called "{name}".', "Rename or delete the extra ones in the web app."
        )
    project: dict[str, Any] = matches[0]
    return project


def with_defaults(params: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """The same benchmark defaults the web app fills in: temperature 0 and a fixed seed, where accepted."""
    supported = set(profile.get("parameters", {}))
    return {**{k: v for k, v in DEFAULTS.items() if k in supported and k not in params}, **params}


def link(base_url: str, project_id: str, experiment_id: str) -> str:
    return f"{base_url}/projects/{project_id}/results?experiment={experiment_id}"


def _signature(experiment: dict[str, Any]) -> list[tuple[str, str, int, str]]:
    models = experiment["configuration"]["models"]
    return sorted((m["provider"], m["model"], m["runs"], json.dumps(m["params"], sort_keys=True)) for m in models)


class Runner:
    def __init__(
        self,
        api: ApiClient,
        loaded: Loaded,
        base_url: str,
        *,
        yes: bool = False,
        ci: bool = False,
        max_cost: Decimal | None = None,
        interactive: bool | None = None,
        timeout_s: float = TIMEOUT_S,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.api = api
        self.loaded = loaded
        self.base_url = base_url
        self.yes = yes
        self.ci = ci
        self.max_cost = max_cost
        self.interactive = sys.stdin.isatty() and sys.stderr.isatty() if interactive is None else interactive
        self.timeout_s = timeout_s
        self.sleep = sleep
        self.clock = clock

    # -- run -------------------------------------------------------------------------------------

    def run(self, only: str | None) -> list[EntryResult]:
        chosen = _choose(self.loaded, only)
        results = []
        for prompt in chosen:
            ui.info(f"\n{prompt.entry.name}  →  {prompt.project_name}")
            result = EntryResult(prompt.entry.name, prompt.project_name)
            try:
                self._one(prompt, result)
            except CliError as error:
                result.error = error.message
                ui.fail(error)
            results.append(result)
        return results

    def _one(self, prompt: ResolvedPrompt, result: EntryResult) -> None:
        entry = prompt.entry
        project = find_project(self.api, prompt.project_name)
        pid = result.project_id = str(project["id"])
        version = self._approved_cases(pid)
        profiles = self.api.pages(f"/projects/{pid}/models")
        models = [
            {"model_profile_id": p["id"], "runs": entry.runs, "params": with_defaults(entry.params.given(), p)}
            for p in (resolve_model(name, profiles) for name in entry.models)
        ]
        body: dict[str, Any] = {
            "name": f"{entry.name} · CLI run",
            "dataset_version_id": version["id"],
            "split_scope": "all",
            "models": models,
            "budget_cap": str(entry.budget) if entry.budget else None,
        }
        if entry.judge:
            judge = resolve_model(entry.judge, profiles)
            body["judge"] = {"credential_id": judge["credential_id"], "model": judge["model_name"]}
        estimate = self.api.post(f"/projects/{pid}/experiments/estimate", body)
        self._show_estimate(estimate, entry.budget)
        self._confirm(estimate)
        experiment = self.api.post(f"/projects/{pid}/experiments", body)
        result.experiment_id = str(experiment["id"])
        result.link = link(self.base_url, pid, result.experiment_id)
        ui.info(f"Started. Watch it live: {result.link}")
        finished = self._wait_for_answers(pid, result.experiment_id)
        result.status = finished["status"]
        scored = self._wait_for_scores(pid, result.experiment_id)
        result.models = scored["models"]
        for line in results_table(result.models):
            typer.echo(line, err=True)
        ui.info(f"Results: {result.link}")
        self._judge(entry, finished, result, pid)

    def _approved_cases(self, project_id: str) -> dict[str, Any]:
        try:
            version: dict[str, Any] = self.api.get(f"/projects/{project_id}/dataset-versions/current")
        except CliError as error:
            if error.status == 404:
                raise CliError(
                    "This project has no test cases.", "Run `verano push` (with `data:` in verano.yaml)."
                ) from error
            raise
        if version["status"] != "approved":
            raise CliError(
                f"The latest test cases (version {version['version']}) are not approved yet.",
                "Run `verano push`, or approve them in the web app.",
            )
        return version

    def _show_estimate(self, estimate: dict[str, Any], budget: Decimal | None) -> None:
        ui.info(f"{estimate['calls']} model calls on {estimate['cases']} test cases.")
        ui.info(
            f"Estimated cost: {money(estimate['total_cost'])}"
            f" (answers {money(estimate['generation_cost'])}, scoring {money(estimate['judge_cost'])})"
        )
        if budget is not None:
            cost = estimate["total_cost"]
            over = cost is not None and Decimal(str(cost)) > budget
            ui.info(f"Budget cap: {money(budget)}" + (" — the run will stop when it is spent." if over else ""))

    def _confirm(self, estimate: dict[str, Any]) -> None:
        cost = estimate["total_cost"]
        if self.max_cost is not None:
            if cost is None:
                raise CliError("The price of some models is unknown, so --max-cost can't be checked.")
            if Decimal(str(cost)) > self.max_cost:
                raise CliError(
                    f"The estimate {money(cost)} is over --max-cost {money(self.max_cost)}. Nothing was started."
                )
        if self.yes or self.ci:
            return
        if not self.interactive:
            raise CliError("Not starting without your confirmation.", "Add --yes (or --ci) to run in a script.")
        if not typer.confirm("Start the run?", err=True):
            raise click.exceptions.Abort()

    def _cancel(self, project_id: str, experiment_id: str) -> None:
        try:
            self.api.post(f"/projects/{project_id}/experiments/{experiment_id}/cancel")
            ui.info("Stopped the experiment; calls already made are kept.")
        except CliError:
            ui.warn("Could not stop the experiment. Stop it from the web app so it stops spending.")

    def _wait_for_answers(self, project_id: str, experiment_id: str) -> dict[str, Any]:
        deadline, last = self.clock() + self.timeout_s, -PROGRESS_S
        try:
            while True:
                experiment: dict[str, Any] = self.api.get(f"/projects/{project_id}/experiments/{experiment_id}")
                now = self.clock()
                if experiment["status"] in FINISHED:
                    return experiment
                if now - last >= PROGRESS_S:
                    done = sum(p["succeeded"] + p["failed"] + p["skipped"] for p in experiment["progress"])
                    spent = sum(Decimal(str(p["cost"])) for p in experiment["progress"])
                    ui.info(f"  {done}/{experiment['total_calls']} calls · {money(spent)} so far")
                    last = now
                if now > deadline:
                    self._cancel(project_id, experiment_id)
                    raise CliError(
                        f"The run did not finish within {int(self.timeout_s)} seconds.", "Use --timeout to wait longer."
                    )
                self.sleep(POLL_S)
        except KeyboardInterrupt:
            self._cancel(project_id, experiment_id)
            raise

    def _wait_for_scores(self, project_id: str, experiment_id: str) -> dict[str, Any]:
        deadline = self.clock() + self.timeout_s
        while True:
            results: dict[str, Any] = self.api.get(f"/projects/{project_id}/experiments/{experiment_id}/results")
            if results["evaluation_run"] is not None:
                return results
            runs = results.get("evaluation_runs", [])
            if runs and all(r["status"] == "failed" for r in runs):
                raise CliError(
                    "Scoring the answers failed.", "Check `docker compose logs worker`, then rescore in the web app."
                )
            if self.clock() > deadline:
                raise CliError("Scoring did not finish in time.", "The answers are saved; open the link above later.")
            self.sleep(POLL_S)

    def _baseline(self, project_id: str, finished: dict[str, Any]) -> dict[str, float] | None:
        """The quality per model in the latest earlier run with the same models and settings on the same cases."""
        wanted = _signature(finished)
        earlier = self.api.get(f"/projects/{project_id}/experiments", limit=50)["items"]
        for other in earlier:
            same = other["id"] != finished["id"] and other["status"] == "completed" and other["origin"] == "manual"
            if same and other["dataset_version_id"] == finished["dataset_version_id"] and _signature(other) == wanted:
                scored = self.api.get(f"/projects/{project_id}/experiments/{other['id']}/results")
                if scored["evaluation_run"] is not None:
                    return {m["model"]: float(m["quality"]) for m in scored["models"]}
        return None

    def _judge(self, entry: Any, finished: dict[str, Any], result: EntryResult, project_id: str) -> None:
        gate = entry.gate
        if gate is None:
            if self.ci:
                ui.info("No `gate:` for this prompt, so there is nothing to enforce.")
            return
        baseline = self._baseline(project_id, finished) if gate.max_drop is not None else None
        verdict = evaluate(
            gate, result.models, finished["status"] == "completed", finished.get("stop_reason"), baseline
        )
        result.verdict = verdict
        for note in verdict.notes:
            ui.info(note)
        if verdict.passed:
            ui.ok("Quality gate passed.")
            return
        for failure in verdict.failures:
            ui.warn(failure)
        if self.ci:
            ui.warn("Quality gate failed.")
        else:
            ui.info("(This would fail the gate under `verano run --ci`.)")


def _choose(loaded: Loaded, only: str | None) -> list[ResolvedPrompt]:
    chosen = [p for p in loaded.prompts if only in (None, p.entry.name)]
    if only and not chosen:
        names = ", ".join(p.entry.name for p in loaded.prompts)
        raise CliError(f"verano.yaml has no prompt called '{only}'.", f"Its prompts: {names}")
    return chosen


def exit_for(results: list[EntryResult], ci: bool) -> None:
    """Raises when the run should end in a non-zero exit: an error (1), or with --ci a failed gate (2)."""
    failed = [r for r in results if r.error]
    if failed:
        raise CliError(
            f"{len(failed)} of {len(results)} prompts could not be run: {', '.join(r.name for r in failed)}."
        )
    gated = [r for r in results if r.verdict is not None and not r.verdict.passed]
    if gated and ci:
        raise GateFailed(f"The quality gate failed for: {', '.join(r.name for r in gated)}.")


def as_json(results: list[EntryResult]) -> str:
    return json.dumps(
        {
            "passed": all(r.error is None and (r.verdict is None or r.verdict.passed) for r in results),
            "prompts": [
                {
                    "name": r.name,
                    "project": r.project,
                    "experiment_id": r.experiment_id,
                    "link": r.link,
                    "status": r.status,
                    "error": r.error,
                    "models": r.models,
                    "gate": None if r.verdict is None else {"passed": r.verdict.passed, "failures": r.verdict.failures},
                }
                for r in results
            ],
        },
        indent=2,
    )


# -- status ----------------------------------------------------------------------------------------


def status(api: ApiClient, loaded: Loaded, base_url: str, only: str | None) -> None:
    for prompt in _choose(loaded, only):
        typer.echo(f"{prompt.entry.name}  →  {prompt.project_name}")
        try:
            project = find_project(api, prompt.project_name)
        except CliError as error:
            typer.echo(f"  {error.message}")
            continue
        items = api.get(f"/projects/{project['id']}/experiments", limit=20)["items"]
        manual = [e for e in items if e["origin"] == "manual"]
        running = next((e for e in manual if e["status"] in {"planned", "running", "evaluating"}), None)
        done = next((e for e in manual if e["status"] == "completed"), None)
        if running:
            typer.echo(f"  A run is in progress: {link(base_url, project['id'], running['id'])}")
        if done is None:
            typer.echo("  No finished run yet. Start one with `verano run`.")
            continue
        scored = api.get(f"/projects/{project['id']}/experiments/{done['id']}/results")
        when = (done.get("completed_at") or done["created_at"])[:16].replace("T", " ")
        typer.echo(f"  Latest run: {when} · configuration {done['configuration']['hash'][:8]}")
        for line in results_table(scored["models"]):
            typer.echo(f"  {line}")
        typer.echo(f"  {link(base_url, project['id'], done['id'])}")


# -- command entry points ----------------------------------------------------------------------------


def command(
    file: Any, only: str | None, ci: bool, yes: bool, max_cost: float | None, timeout: int, json_output: bool
) -> None:

    loaded = load(file or find_file())
    credentials = auth.signed_in()
    api = ApiClient.from_credentials(credentials)
    cap = Decimal(str(max_cost)) if max_cost is not None else None
    results = Runner(api, loaded, credentials.url, yes=yes, ci=ci, max_cost=cap, timeout_s=float(timeout)).run(only)
    if json_output:
        typer.echo(as_json(results))
    exit_for(results, ci)


def status_command(file: Any, only: str | None) -> None:

    credentials = auth.signed_in()
    status(ApiClient.from_credentials(credentials), load(file or find_file()), credentials.url, only)
