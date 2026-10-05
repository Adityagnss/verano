"""
The test cases part of `verano push`: bring the files in verano.yaml to an approved dataset.

Steps, each looking at what Verano already holds before doing anything:
  1. the Task Spec you wrote is saved for the current prompt version (no model call);
  2. if the approved test cases already are these files, and the same task, nothing else happens;
  3. otherwise the files are uploaded (inputs first, then the golden file with its mapping), the
     golden-only generation builds the scoring checks without calling any model, and the cases
     are approved. Your own examples are trusted by definition, so there is nothing to review.

A new set of test cases is a new dataset version: old experiments keep the version they ran on.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from verano import ui
from verano.cases import GOLDEN_MAPPING, case_file, golden_file, sha256
from verano.client import ApiClient
from verano.errors import CliError
from verano.loader import ResolvedPrompt

POLL_S = 0.5
WAIT_S = 300.0
REAL_INPUTS = {"attachment", "user_message"}
PROGRESS_EVERY = 25


@dataclass(frozen=True)
class Upload:
    name: str
    content: bytes
    purpose: str  # "input" or "golden"

    @property
    def digest(self) -> str:
        return sha256(self.content)


@dataclass(frozen=True)
class Plan:
    inputs: list[Upload]
    golden: Upload | None
    mapping: dict[str, Any] | None  # None: ask Verano to suggest one
    cases: int

    @property
    def uploads(self) -> list[Upload]:
        return [*self.inputs, *([self.golden] if self.golden else [])]

    @property
    def digests(self) -> set[str]:
        return {u.digest for u in self.uploads}


def make_plan(prompt: ResolvedPrompt) -> Plan | None:
    data = prompt.entry.data
    if prompt.cases is not None:
        cases = prompt.cases.cases
        inputs = [Upload(c.filename, case_file(c), "input") for c in cases]
        return Plan(inputs, Upload("golden.csv", golden_file(cases), "golden"), dict(GOLDEN_MAPPING), len(cases))
    if not prompt.inputs and prompt.golden is None:
        return None
    inputs = [Upload(p.name, p.read_bytes(), "input") for p in prompt.inputs]
    names = [u.name for u in inputs]
    clash = sorted({n for n in names if names.count(n) > 1})
    if clash:
        raise CliError(
            f"Two input files are both called {', '.join(clash)}.",
            "Verano pairs answers with files by name; rename one of them.",
        )
    golden = Upload(prompt.golden.name, prompt.golden.read_bytes(), "golden") if prompt.golden else None
    mapping = None
    if data.columns is not None:
        mapping = {k: v for k, v in data.columns.model_dump().items() if v not in (None, [])}
    return Plan(inputs, golden, mapping, len(inputs))


def check_prompt_fits(version: dict[str, Any]) -> None:
    extra = sorted(set(version.get("required_inputs", [])) - REAL_INPUTS)
    if extra:
        names = ", ".join("{{ " + n + " }}" for n in extra)
        raise CliError(
            f"The prompt needs {names}, but test cases made from files provide only `attachment` "
            "(and `user_message` when the prompt is system-only).",
            "Write {{ attachment }} where each test case's input goes, or use only a system prompt.",
        )


def _task_body(prompt: ResolvedPrompt) -> dict[str, Any]:
    task = prompt.entry.task
    return {
        "task_type": task.type,
        "goal": task.goal,
        "output_format": task.output_format,
        "allowed_outputs": task.allowed_outputs,
        "output_schema": task.output_schema,
        "constraints": task.constraints,
        "risk_areas": task.risks,
    }


class DataSync:
    def __init__(
        self,
        api: ApiClient,
        project_id: str | None,
        prompt: ResolvedPrompt,
        say: Callable[[str, str | None], None],
        dry_run: bool,
        replace_draft: bool = False,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.api = api
        self.project_id = project_id
        self.prompt = prompt
        self.say = say
        self.dry = dry_run
        self.replace_draft = replace_draft
        self.sleep = sleep
        self.clock = clock

    # -- the whole step ---------------------------------------------------------------------

    def run(self, version: dict[str, Any] | None, judge: dict[str, Any] | None) -> None:
        plan = make_plan(self.prompt)
        if plan is None:
            self.say("no test cases in verano.yaml (add `data:`, or add them in the web app)", None)
            return
        if self.project_id is None or version is None:
            self.say("", f"save the Task Spec and upload {plan.cases} test cases")
            return
        check_prompt_fits(version)
        current = self._current()
        files = self.api.pages(f"/projects/{self.project_id}/input-files")
        attached = [f for f in files if current and f["dataset_version_id"] == current["id"]]
        digests = {f["sha256"] for f in attached}
        same_data = digests == plan.digests and all(f["status"] == "imported" for f in attached)
        if self.dry:
            self._dry(plan, current, same_data)
            return
        spec = self._provide_spec(version, judge)
        if same_data and current and current["status"] == "approved" and self._same_task(current, spec):
            self.say(f"test cases unchanged ({plan.cases} cases, approved)", None)
            return
        draft = current if current and current["status"] == "draft" else None
        resume = bool(draft) and same_data
        if draft and not resume:
            self._clear_draft(attached, plan)
        if not resume:
            self._upload(plan)
        self._approve(spec, judge)

    def _dry(self, plan: Plan, current: dict[str, Any] | None, same_data: bool) -> None:
        if same_data and current and current["status"] == "approved":
            self.say("", "keep the approved test cases (the files are unchanged)")
        else:
            self.say("", f"upload {plan.cases} test cases and approve them as a new dataset version")

    # -- reading -----------------------------------------------------------------------------

    def _current(self) -> dict[str, Any] | None:
        try:
            current: dict[str, Any] = self.api.get(f"/projects/{self.project_id}/dataset-versions/current")
            return current
        except CliError as error:
            if error.status == 404:
                return None
            raise

    def _provide_spec(self, version: dict[str, Any], judge: dict[str, Any] | None) -> dict[str, Any]:
        body: dict[str, Any] = {"spec": _task_body(self.prompt)}
        if judge is not None:
            body["judge"] = {"credential_id": judge["credential_id"], "model": judge["model_name"]}
        spec: dict[str, Any] = self.api.put(
            f"/projects/{self.project_id}/prompt-versions/{version['id']}/task-spec", body
        )
        for warning in spec.get("warnings", []):
            ui.warn(warning)
        return spec

    def _same_task(self, current: dict[str, Any], spec: dict[str, Any]) -> bool:
        if not current.get("task_spec_id"):
            return False
        if current["task_spec_id"] == spec["id"]:
            return True
        used = self.api.get(f"/projects/{self.project_id}/task-specs/{current['task_spec_id']}")
        keys = ("spec", "generator_credential_id", "generator_model")
        return all(used.get(k) == spec.get(k) for k in keys)

    # -- changing ----------------------------------------------------------------------------

    def _clear_draft(self, attached: list[dict[str, Any]], plan: Plan) -> None:
        foreign = [f for f in attached if f["sha256"] not in plan.digests]
        if foreign and not self.replace_draft:
            names = ", ".join(f["filename"] for f in foreign[:3]) + ("…" if len(foreign) > 3 else "")
            raise CliError(
                f"This project has unapproved test cases that are not in verano.yaml ({names}).",
                "Review them in the web app, or run `verano push --replace-draft` to replace them with the file's.",
            )
        for f in attached:
            self.api.delete(f"/projects/{self.project_id}/input-files/{f['id']}")

    def _upload_one(self, upload: Upload) -> str:
        made = self.api.request(
            "POST",
            f"/projects/{self.project_id}/input-files",
            files={"file": (upload.name, upload.content, "application/octet-stream")},
            data={"purpose": upload.purpose},
        )
        return str(made["id"])

    def _upload(self, plan: Plan) -> None:
        ids = []
        total = len(plan.inputs)
        for number, upload in enumerate(plan.inputs, start=1):
            ids.append(self._upload_one(upload))
            if total >= PROGRESS_EVERY and number % PROGRESS_EVERY == 0:
                ui.info(f"  uploading test cases… {number}/{total}")
        self._wait(set(ids), {"imported"}, "test cases")
        if plan.golden is None:
            self.say(f"{total} test cases uploaded", None)
            return
        golden_id = self._upload_one(plan.golden)
        self._wait({golden_id}, {"ready"}, "the golden file")
        mapping = (
            plan.mapping
            or self.api.get(f"/projects/{self.project_id}/input-files/{golden_id}/mapping-suggestion")["mapping"]
        )
        self.api.put(f"/projects/{self.project_id}/input-files/{golden_id}/mapping", {"mapping": mapping})
        checked = self._wait({golden_id}, {"validated"}, "the golden file's columns")[golden_id]
        report = checked.get("validation_report") or {}
        for issue in report.get("issues", []):
            ui.warn(f"golden file: {issue['message']} ({issue['count']} rows)")
        if not report.get("valid_rows"):
            raise CliError("Verano found no usable row in the golden file.", "Check the column names under `columns:`.")
        self.api.post(f"/projects/{self.project_id}/input-files/{golden_id}/import")
        imported = self._wait({golden_id}, {"imported"}, "the import")[golden_id]
        self.say(f"{total} test cases uploaded, {imported.get('imported_rows', 0)} paired with an answer", None)

    def _wait(self, ids: set[str], done: set[str], what: str) -> dict[str, dict[str, Any]]:
        deadline = self.clock() + WAIT_S
        while True:
            seen = {f["id"]: f for f in self.api.pages(f"/projects/{self.project_id}/input-files") if f["id"] in ids}
            for f in seen.values():
                if f["status"] == "failed":
                    raise CliError(f"{f['filename']}: {f.get('error_message') or 'Verano could not read this file.'}")
            if len(seen) == len(ids) and all(f["status"] in done for f in seen.values()):
                return seen
            if self.clock() > deadline:
                raise CliError(
                    f"Verano didn't finish processing {what} within {int(WAIT_S)} seconds.",
                    "Is the worker running? Check `docker compose logs worker`, then run the push again.",
                )
            self.sleep(POLL_S)

    def _approve(self, spec: dict[str, Any], judge: dict[str, Any] | None) -> None:
        pid = self.project_id
        started = self.api.post(f"/projects/{pid}/generations", {"task_spec_id": spec["id"], "golden_only": True})
        version_id = started["id"]
        deadline = self.clock() + WAIT_S
        while True:
            version = self.api.get(f"/projects/{pid}/dataset-versions/{version_id}")
            state = (version.get("generation") or {}).get("status", "succeeded")
            if state == "failed":
                raise CliError(
                    f"Preparing the test cases failed: {version['generation'].get('message', 'unknown error')}"
                )
            if state != "running":
                break
            if self.clock() > deadline:
                raise CliError("Preparing the test cases is taking too long.", "Check `docker compose logs worker`.")
            self.sleep(POLL_S)
        evaluators = self.api.get(f"/projects/{pid}/dataset-versions/{version_id}/evaluators")["evaluators"]
        if judge is None and any(e["config"].get("kind") == "deepeval" for e in evaluators):
            ui.warn("These test cases are scored partly by a judge model. Add `judge:` so Verano can score them.")
        approved = self.api.post(f"/projects/{pid}/dataset-versions/{version_id}/approve")
        held = approved.get("by_split", {}).get("holdout", 0)
        self.say(f"test cases approved: {approved['item_count']} cases ({held} held back to check improvements)", None)
        for note in approved.get("warnings", []):
            ui.warn(note)


def display_path(path: Path, root: Path) -> str:
    return str(path.relative_to(root.resolve()))
