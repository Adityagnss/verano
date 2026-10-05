"""An in-memory Verano for `push` and `run` tests: projects, keys, models and prompts."""

import json
from dataclasses import dataclass, field
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
        body = json.loads(request.content) if request.content else {}
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
        return {
            "id": self.next_id("v"),
            "version": number,
            "system_template": body.get("system_template"),
            "user_template": body.get("user_template"),
            "default_params": body.get("default_params", {}),
            "change_reason": body.get("change_reason"),
        }

    def prompt_route(self, pid: str, method: str, body: dict[str, Any], request: httpx.Request) -> httpx.Response:
        if method == "GET":
            return self.page(self.prompts.get(pid, []), request)
        prompt = {"id": self.next_id("pr"), "name": body["name"], "latest_version": self.version(1, body)}
        self.prompts.setdefault(pid, []).append(prompt)
        return httpx.Response(201, json=prompt)
