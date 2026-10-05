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
        if not path.startswith("/auth") and bearer not in {t["token"] for t in self.tokens.values()}:
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
        data = self.data_route(pid, rest, method, body, request)
        if data is not None:
            return data
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
                "id": self.next_id("dv"), "status": "draft", "task_spec_id": None, "item_count": 0,
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
