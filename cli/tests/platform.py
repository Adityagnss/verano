"""An in-memory Verano for `push` and `run` tests: projects, keys, models and prompts."""

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from email.message import Message
from email.parser import BytesParser
from typing import Any

import httpx

from tests.conftest import FakeVerano, error

CATALOG = {
    "openai": ["gpt-4o-mini", "gpt-4o"],
    "anthropic": ["claude-haiku"],
    "ollama": ["llama3"],
    "groq": ["gpt-4o-mini"],
}


@dataclass
class FakePlatform(FakeVerano):
    page_size: int = 2
    projects: list[dict[str, Any]] = field(default_factory=list)
    credentials: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    profiles: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    prompts: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    secrets: list[str] = field(default_factory=list)
    counter: int = 0
    files: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    contents: dict[str, bytes] = field(default_factory=dict)
    versions: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    specs: dict[str, dict[str, Any]] = field(default_factory=dict)
    evaluator_kinds: list[str] = field(default_factory=lambda: ["exact_match"])
    stuck: bool = False
    used_prompts: set[str] = field(default_factory=set)
    labels: dict[tuple[str, str], str] = field(default_factory=dict)
    experiments: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    started: list[dict[str, Any]] = field(default_factory=list)
    quality: dict[str, float] = field(default_factory=dict)
    latency: dict[str, float] = field(default_factory=dict)
    call_cost: dict[str, str] = field(default_factory=dict)
    price: str | None = "0.0420"
    stop_reason: str | None = None
    stall: bool = False
    score_polls: int = 1
    scoring_failed: bool = False

    def next_id(self, prefix: str) -> str:
        self.counter += 1
        return f"{prefix}{self.counter}"

    @property
    def writes(self) -> list[tuple[str, str]]:
        return [c for c in self.calls if c[0] in {"POST", "PUT", "PATCH", "DELETE"} and not c[1].startswith("/auth")]

    def page(self, items: list[Any], request: httpx.Request) -> httpx.Response:
        start = int(request.url.params.get("cursor") or 0)
        size = min(int(request.url.params.get("limit") or self.page_size), self.page_size)
        chunk = items[start : start + size]
        more = str(start + size) if start + size < len(items) else None
        return httpx.Response(200, json={"items": chunk, "next_cursor": more})

    def add_project(self, name: str) -> dict[str, Any]:
        project = {"id": self.next_id("p"), "name": name}
        self.projects.append(project)
        return project

    def route(self, request: httpx.Request, path: str) -> httpx.Response:
        bearer = request.headers.get("authorization", "").removeprefix("Bearer ")
        known = {t["token"] for t in self.tokens.values()} | {"session-jwt"}
        if not path.startswith("/auth") and bearer not in known:
            return error(401, "This API token is invalid, expired or revoked.")
        is_json = request.headers.get("content-type", "").startswith("application/json")
        body = json.loads(request.content) if request.content and is_json else {}
        method = request.method
        if path == "/providers":
            return httpx.Response(200, json=[{"name": n} for n in CATALOG])
        if path == "/projects":
            if method == "GET":
                return self.page(list(reversed(self.projects)), request)
            return httpx.Response(201, json=self.add_project(body["name"]))
        parts = path.strip("/").split("/")
        if parts[0] != "projects":
            return super().route(request, path)
        pid, rest = parts[1], "/" + "/".join(parts[2:])
        if rest == "/credentials":
            return self.credential_route(pid, method, body)
        if rest.startswith("/credentials/") and method == "PATCH":
            stored = next(c for c in self.credentials[pid] if c["id"] == rest.rsplit("/", 1)[1])
            if body.get("api_key"):
                self.secrets.append(body["api_key"])
                stored["key_last4"] = body["api_key"][-4:]
            return httpx.Response(200, json=stored)
        if rest == "/models" and method == "GET":
            return self.page(self.profiles.get(pid, []), request)
        if rest == "/models/selection" and method == "PUT":
            for profile in self.profiles.get(pid, []):
                if profile["id"] in body["selected"]:
                    profile["is_selected"] = True
                if profile["id"] in body["unselected"]:
                    profile["is_selected"] = False
            return httpx.Response(204)
        if rest == "/prompts":
            return self.prompt_route(pid, method, body, request)
        experiment = self.experiment_route(pid, rest, method, body, request)
        if experiment is not None:
            return experiment
        data = self.data_route(pid, rest, method, body, request)
        if data is not None:
            return data
        if parts[2] == "prompts" and len(parts) == 4 and method == "DELETE":
            if request.url.params.get("confirm") != "true":
                return error(422, "Send confirm=true to go ahead.")
            if parts[3] in self.used_prompts:
                return error(409, "This prompt has been tested in 1 experiment(s).")
            self.prompts[pid] = [p for p in self.prompts[pid] if p["id"] != parts[3]]
            return httpx.Response(204)
        if parts[2] == "prompts" and len(parts) == 6 and parts[4] == "labels" and method == "PUT":
            self.labels[(parts[3], parts[5])] = body["version_id"]
            return httpx.Response(200, json={"name": parts[5], "version_id": body["version_id"]})
        if parts[2] == "prompts" and len(parts) == 5 and parts[4] == "versions" and method == "POST":
            prompt = next(p for p in self.prompts[pid] if p["id"] == parts[3])
            version = self.version(prompt["latest_version"]["version"] + 1, body)
            prompt["latest_version"] = version
            return httpx.Response(201, json=version)
        return super().route(request, path)

    def credential_route(self, pid: str, method: str, body: dict[str, Any]) -> httpx.Response:
        if method == "GET":
            return httpx.Response(200, json=self.credentials.get(pid, []))
        secret = body.get("api_key")
        if secret:
            self.secrets.append(secret)
        if secret == "rejected-key":
            return error(422, "The OpenAI key was rejected. Check it and try again.")
        credential = {
            "id": self.next_id("c"),
            "provider": body["provider"],
            "key_last4": secret[-4:] if secret else None,
            "model_count": len(CATALOG[body["provider"]]),
        }
        self.credentials.setdefault(pid, []).append(credential)
        for name in CATALOG[body["provider"]]:
            self.profiles.setdefault(pid, []).append(
                {
                    "id": self.next_id("m"),
                    "credential_id": credential["id"],
                    "provider": body["provider"],
                    "model_name": name,
                    "display_name": name,
                    "parameters": {"temperature": {}, "seed": {}}
                    if body["provider"] == "openai"
                    else {"temperature": {}},
                    "is_selected": False,
                }
            )
        return httpx.Response(201, json=credential)

    def version(self, number: int, body: dict[str, Any]) -> dict[str, Any]:
        system, user = body.get("system_template"), body.get("user_template")
        names = set(re.findall(r"\{\{\s*(\w+)\s*\}\}", f"{system or ''} {user or ''}"))
        required = sorted(names | ({"user_message"} if system and not user else set()))
        return {
            "id": self.next_id("v"),
            "version": number,
            "system_template": system,
            "user_template": user,
            "default_params": body.get("default_params", {}),
            "change_reason": body.get("change_reason"),
            "required_inputs": required,
        }

    def prompt_route(self, pid: str, method: str, body: dict[str, Any], request: httpx.Request) -> httpx.Response:
        if method == "GET":
            return self.page(self.prompts.get(pid, []), request)
        prompt = {"id": self.next_id("pr"), "name": body["name"], "latest_version": self.version(1, body)}
        self.prompts.setdefault(pid, []).append(prompt)
        return httpx.Response(201, json=prompt)

    # -- test cases ------------------------------------------------------------------------

    def latest(self, pid: str) -> dict[str, Any] | None:
        versions = self.versions.get(pid, [])
        return versions[-1] if versions else None

    def draft(self, pid: str) -> dict[str, Any]:
        latest = self.latest(pid)
        if latest is None or latest["status"] == "approved":
            latest = {
                "id": self.next_id("dv"), "version": len(self.versions.get(pid, [])) + 1, "status": "draft",
                "task_spec_id": None, "item_count": 0,
                "by_split": {}, "generation": None, "warnings": [],
            }  # fmt: skip
            self.versions.setdefault(pid, []).append(latest)
        return latest

    def advance(self, pid: str) -> None:
        """One more poll: the background workers move every file one step along."""
        if self.stuck:
            return
        for f in self.files.get(pid, []):
            if f["status"] == "uploaded":
                if f["kind"] == "raw_inputs":
                    f["status"] = "imported"
                    f["dataset_version_id"] = self.draft(pid)["id"]
                    self.draft(pid)["item_count"] += 1
                else:
                    f["status"] = "ready"
            elif f["status"] == "validating":
                f["status"] = "validated"
            elif f["status"] == "importing":
                f["status"] = "imported"
                f["dataset_version_id"] = self.draft(pid)["id"]

    def data_route(
        self, pid: str, rest: str, method: str, body: dict[str, Any], request: httpx.Request
    ) -> httpx.Response | None:
        if rest == "/input-files" and method == "GET":
            self.advance(pid)
            return self.page(self.files.get(pid, []), request)
        if rest == "/input-files" and method == "POST":
            return self.upload(pid, request)
        if rest.startswith("/input-files/"):
            return self.file_route(pid, rest.split("/")[2], rest.split("/")[3:], method, body)
        if rest == "/dataset-versions/current":
            latest = self.latest(pid)
            return httpx.Response(200, json=latest) if latest else error(404, "There is no dataset yet.")
        if rest.startswith("/dataset-versions/"):
            return self.version_route(pid, rest.split("/")[2], rest.split("/")[3:], method)
        if rest.startswith("/prompt-versions/") and rest.endswith("/task-spec") and method == "PUT":
            return self.provide_spec(pid, rest.split("/")[2], body)
        if rest.startswith("/task-specs/") and method == "GET":
            return httpx.Response(200, json=self.specs[rest.split("/")[2]])
        if rest == "/generations" and method == "POST":
            draft = self.draft(pid)
            draft["task_spec_id"] = body["task_spec_id"]
            draft["generation"] = {"status": "succeeded"}
            return httpx.Response(202, json=draft)
        return None

    def upload(self, pid: str, request: httpx.Request) -> httpx.Response:
        header = f"Content-Type: {request.headers['content-type']}\r\n\r\n".encode()
        message = BytesParser().parsebytes(header + request.content)
        fields: dict[str, Any] = {}
        parts = message.get_payload()
        assert isinstance(parts, list)
        for part in parts:
            assert isinstance(part, Message)
            name = part.get_param("name", header="content-disposition")
            fields[str(name)] = (part.get_filename(), part.get_payload(decode=True))
        filename, content = fields["file"]
        purpose = fields["purpose"][1].decode()
        record = {
            "id": self.next_id("f"), "kind": "raw_inputs" if purpose == "input" else "golden_set",
            "status": "uploaded", "filename": filename, "size_bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(), "dataset_version_id": None,
            "imported_rows": None, "validation_report": None, "error_message": None,
        }  # fmt: skip
        self.files.setdefault(pid, []).append(record)
        self.contents[record["id"]] = content
        return httpx.Response(201, json=record)

    def file_route(self, pid: str, file_id: str, rest: list[str], method: str, body: dict[str, Any]) -> httpx.Response:
        record = next((f for f in self.files.get(pid, []) if f["id"] == file_id), None)
        if record is None:
            return error(404, "This file doesn't exist.")
        if not rest and method == "DELETE":
            self.files[pid].remove(record)
            version = next((v for v in self.versions.get(pid, []) if v["id"] == record["dataset_version_id"]), None)
            if version and record["kind"] == "raw_inputs":
                version["item_count"] -= 1
            return httpx.Response(204)
        if rest == ["mapping-suggestion"]:
            return httpx.Response(200, json={"mapping": {"expected_output": "expected"}})
        if rest == ["mapping"] and method == "PUT":
            rows = list(csv.DictReader(io.StringIO(self.contents[file_id].decode())))
            record["status"] = "validating"
            record["column_mapping"] = body["mapping"]
            issues = []
            inputs = [f for f in self.files[pid] if f["kind"] == "raw_inputs"]
            if len(rows) > len(inputs):
                issues.append(
                    {
                        "kind": "unpaired",
                        "message": "Some rows match no input file.",
                        "count": len(rows) - len(inputs),
                        "rows": [],
                    }
                )
            record["validation_report"] = {"valid_rows": len(rows) if rows else 0, "skipped_rows": 0, "issues": issues}
            return httpx.Response(200, json=record)
        if rest == ["import"] and method == "POST":
            record["status"] = "importing"
            record["imported_rows"] = record["validation_report"]["valid_rows"]
            return httpx.Response(200, json=record)
        return error(404, "Not found.")

    def version_route(self, pid: str, version_id: str, rest: list[str], method: str) -> httpx.Response:
        version = next(v for v in self.versions[pid] if v["id"] == version_id)
        if not rest:
            return httpx.Response(200, json=version)
        if rest == ["evaluators"]:
            return httpx.Response(
                200, json={"evaluators": [{"name": k, "config": {"kind": k}} for k in self.evaluator_kinds]}
            )
        if rest == ["approve"] and method == "POST":
            if version["item_count"] == 0:
                return error(422, "There are no test cases yet.", problems=["Add test cases before approving."])
            version["status"] = "approved"
            version["by_split"] = {
                "holdout": version["item_count"] * 3 // 10,
                "optimize": version["item_count"] - version["item_count"] * 3 // 10,
            }
            version["warnings"] = ["Only a few cases are held back for checks."] if version["item_count"] < 40 else []
            return httpx.Response(200, json=version)
        return error(404, "Not found.")

    def provide_spec(self, pid: str, prompt_version_id: str, body: dict[str, Any]) -> httpx.Response:
        judge = body.get("judge")
        content = {
            "spec": body["spec"], "generator_credential_id": judge["credential_id"] if judge else None,
            "generator_model": judge["model"] if judge else None,
        }  # fmt: skip
        key = (prompt_version_id, json.dumps(content, sort_keys=True))
        for existing in self.specs.values():
            if existing["_key"] == key:
                return httpx.Response(200, json=existing)
        record = {"id": self.next_id("ts"), "status": "confirmed", "warnings": [], **content, "_key": key}
        self.specs[record["id"]] = record
        return httpx.Response(200, json=record)

    # -- experiments -----------------------------------------------------------------------

    def model_of(self, pid: str, profile_id: str) -> dict[str, Any]:
        return next(p for p in self.profiles[pid] if p["id"] == profile_id)

    def experiment_route(
        self, pid: str, rest: str, method: str, body: dict[str, Any], request: httpx.Request
    ) -> httpx.Response | None:
        if not rest.startswith("/experiments"):
            return None
        parts = rest.strip("/").split("/")
        if rest == "/experiments/estimate":
            latest = self.latest(pid)
            cases = latest["item_count"] if latest else 0
            calls = cases * sum(m["runs"] for m in body["models"])
            cost = self.price
            return httpx.Response(
                200,
                json={
                    "cases": cases,
                    "calls": calls,
                    "total_cost": cost,
                    "generation_cost": cost,
                    "judge_cost": "0" if cost else None,
                    "price_known": cost is not None,
                },
            )
        if rest == "/experiments" and method == "POST":
            return self.start_experiment(pid, body)
        if rest == "/experiments" and method == "GET":
            return self.page(list(reversed(self.experiments.get(pid, []))), request)
        record = next((e for e in self.experiments.get(pid, []) if e["id"] == parts[1]), None)
        if record is None:
            return error(404, "This experiment doesn't exist in this project.")
        if len(parts) == 2:
            self.advance_experiment(record)
            return httpx.Response(200, json=record)
        if parts[2] == "cancel":
            record["status"] = "cancelled"
            record["stop_reason"] = "Cancelled by the user."
            return httpx.Response(200, json=record)
        if parts[2] == "results":
            return httpx.Response(200, json=self.results(record))
        return None

    def start_experiment(self, pid: str, body: dict[str, Any]) -> httpx.Response:
        self.started.append(body)
        models = [self.model_of(pid, m["model_profile_id"]) for m in body["models"]]
        latest = self.latest(pid)
        assert latest is not None
        cases = latest["item_count"]
        total = cases * sum(m["runs"] for m in body["models"])
        record = {
            "id": self.next_id("e"), "name": body["name"], "status": "running", "origin": "manual",
            "dataset_version_id": body["dataset_version_id"], "total_calls": total, "stop_reason": None,
            "created_at": f"2026-10-05T12:{len(self.experiments.get(pid, [])):02d}:00Z", "completed_at": None,
            "progress": [
                {
                    "model": m["model_name"], "total": cases * r["runs"],
                    "succeeded": 0, "failed": 0, "skipped": 0, "cost": "0",
                }
                for m, r in zip(models, body["models"], strict=True)
            ],
            "configuration": {
                "hash": hashlib.sha256(json.dumps(body["models"], sort_keys=True).encode()).hexdigest(),
                "models": [
                    {"provider": m["provider"], "model": m["model_name"], "runs": r["runs"], "params": r["params"]}
                    for m, r in zip(models, body["models"], strict=True)
                ],
            },
            "polls": 0, "scored": 0, "quality": dict(self.quality),
            "latency": dict(self.latency), "call_cost": dict(self.call_cost),
        }  # fmt: skip
        self.experiments.setdefault(pid, []).append(record)
        return httpx.Response(201, json=record)

    def advance_experiment(self, record: dict[str, Any]) -> None:
        if record["status"] != "running" or self.stall:
            return
        record["polls"] += 1
        for entry in record["progress"]:
            entry["succeeded"] = min(entry["total"], entry["total"] * record["polls"] // 2)
            entry["cost"] = "0.01"
        if record["polls"] >= 2:
            record["status"] = "cancelled" if self.stop_reason else "completed"
            record["stop_reason"] = self.stop_reason
            record["completed_at"] = "2026-10-05T12:30:00Z"

    def results(self, record: dict[str, Any]) -> dict[str, Any]:
        if record["status"] not in {"completed", "cancelled", "failed"}:
            return {"evaluation_run": None, "evaluation_runs": [], "models": []}
        record["scored"] += 1
        if self.scoring_failed:
            return {"evaluation_run": None, "evaluation_runs": [{"status": "failed"}], "models": []}
        if record["scored"] <= self.score_polls - 1:
            return {"evaluation_run": None, "evaluation_runs": [{"status": "running"}], "models": []}
        models = []
        for entry in record["configuration"]["models"]:
            name = entry["model"]
            quality = record["quality"].get(name, 0.9)
            models.append(
                {
                    "model": name, "quality": quality, "pass_rate": quality, "consistency": 1.0,
                    "cases": 3, "judged_cases": 3, "unscored_cases": 0,
                    "stability": 1.0 if entry["runs"] > 1 else None, "latency_ms": record["latency"].get(name, 420.0),
                    "cost_per_call": record["call_cost"].get(name, "0.0014"), "failed_calls": 0,
                }
            )  # fmt: skip
        best = max(models, key=lambda m: (m["quality"], m["model"]), default=None)
        for m in models:
            if m is not best and best is not None:
                gap = m["quality"] - best["quality"]
                m["vs_best"] = {
                    "label": "clear difference" if abs(gap) > 0.2 else "no clear difference",
                    "difference": gap, "cases": 3, "low": None, "high": None,
                }  # fmt: skip
        return {
            "evaluation_run": {"status": "completed"},
            "evaluation_runs": [{"status": "completed"}],
            "models": models,
        }
