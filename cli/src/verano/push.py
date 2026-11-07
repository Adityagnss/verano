"""
`verano push`: make Verano match the prompts in verano.yaml.

For each prompt entry, in this order: the project (found by name, created if missing), the
provider keys named in `keys:` (read from the environment, sent to your own Verano server
exactly as if pasted in the Keys step, never printed or saved), the models, and the prompt
itself. Every step looks at what is already there first, so running it again changes nothing
unless the file changed; a prompt whose text did not change creates no new version.
`--dry-run` reads the same things and reports what would happen without changing anything.
"""

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import click
import typer

from verano import auth, ui
from verano.client import ApiClient
from verano.data import DataSync
from verano.errors import CliError
from verano.loader import Loaded, ResolvedPrompt, find_file, load, normalize_text
from verano.spec import ENV_REFERENCE

MANAGED_BY = "verano push"
KEY_TAIL = 4
HAS_RESULTS_STATUS = 409


@dataclass
class Outcome:
    name: str
    project_name: str
    project_id: str | None = None
    lines: list[str] = field(default_factory=list)
    error: CliError | None = None


def _match_models(wanted: str, profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    exact = [p for p in profiles if wanted in (p["model_name"], f"{p['provider']}/{p['model_name']}")]
    if exact:
        return exact
    lowered = wanted.lower()
    return [p for p in profiles if lowered in (p["model_name"].lower(), p["display_name"].lower())]


def resolve_model(wanted: str, profiles: list[dict[str, Any]]) -> dict[str, Any]:
    matches = _match_models(wanted, profiles)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        options = ", ".join(sorted(f"{p['provider']}/{p['model_name']}" for p in matches))
        raise CliError(
            f"The model '{wanted}' is available from more than one key: {options}.", "Write it as provider/model."
        )
    known = sorted({p["model_name"] for p in profiles})
    shown = ", ".join(known[:12]) + (f", … ({len(known)} in all)" if len(known) > 12 else "")
    raise CliError(
        f"No model called '{wanted}' is available in this project.",
        (f"Available: {shown}. " if known else "No models yet. ")
        + "Add the provider's key under `keys:` in verano.yaml.",
    )


class Pusher:
    def __init__(
        self,
        api: ApiClient,
        loaded: Loaded,
        dry_run: bool,
        env: Mapping[str, str] | None = None,
        with_data: bool = True,
        replace_draft: bool = False,
        label: str | None = None,
        prune: bool = False,
        yes: bool = False,
        interactive: bool | None = None,
    ) -> None:
        self.label = label
        self.prune = prune
        self.yes = yes
        self.interactive = sys.stdin.isatty() and sys.stderr.isatty() if interactive is None else interactive
        self.api = api
        self.loaded = loaded
        self.dry = dry_run
        self.with_data = with_data
        self.replace_draft = replace_draft
        self.env = os.environ if env is None else env
        self._providers: set[str] | None = None
        self._projects: list[dict[str, Any]] | None = None

    def run(self, only: str | None = None) -> list[Outcome]:
        chosen = [p for p in self.loaded.prompts if only in (None, p.entry.name)]
        if only and not chosen:
            names = ", ".join(p.entry.name for p in self.loaded.prompts)
            raise CliError(f"verano.yaml has no prompt called '{only}'.", f"Its prompts: {names}")
        self._check_environment()
        outcomes = []
        for prompt in chosen:
            outcome = Outcome(prompt.entry.name, prompt.project_name)
            ui.info(f"\n{prompt.entry.name}  →  {prompt.project_name}")
            try:
                self._one(prompt, outcome)
            except CliError as error:
                outcome.error = error
                ui.fail(error)
            outcomes.append(outcome)
        return outcomes

    def _say(self, outcome: Outcome, text: str, would: str | None = None) -> None:
        line = (would or text) if self.dry else text
        outcome.lines.append(line)
        (ui.info if self.dry else ui.ok)(("would: " if self.dry and would else "") + line)

    def _check_environment(self) -> None:
        """Every key this file names must be readable before anything is changed."""
        for provider, reference in self.loaded.file.keys.items():
            match = ENV_REFERENCE.match(reference)
            if match and match.group(1) and not self.env.get(match.group(1), "").strip():
                raise CliError(
                    f"The environment variable {match.group(1)} (the {provider} key) is not set or is empty.",
                    "Export it, or remove that line from `keys:`.",
                )

    def _one(self, prompt: ResolvedPrompt, outcome: Outcome) -> None:
        project_id = self._project(prompt, outcome)
        self._keys(project_id, outcome)
        judge = self._models(project_id, prompt, outcome)
        version = self._prompt(project_id, prompt, outcome)
        if self.label:
            self._set_label(project_id, prompt, version, outcome)
        if self.with_data:
            sync = DataSync(
                self.api,
                project_id,
                prompt,
                lambda text, would: self._say(outcome, text, would=would),
                self.dry,
                self.replace_draft,
            )
            sync.run(version, judge)

    def _all_projects(self) -> list[dict[str, Any]]:
        if self._projects is None:
            self._projects = self.api.pages("/projects")
        return self._projects

    def _project(self, prompt: ResolvedPrompt, outcome: Outcome) -> str | None:
        matches = [p for p in self._all_projects() if p["name"] == prompt.project_name]
        if len(matches) > 1:
            raise CliError(
                f'{len(matches)} projects are called "{prompt.project_name}".',
                "Rename or delete the extra ones in the web app, so push knows which to update.",
            )
        if matches:
            outcome.project_id = matches[0]["id"]
            self._say(outcome, "project exists")
            return str(matches[0]["id"])
        if self.dry:
            self._say(outcome, "", would="create the project")
            return None
        created = self.api.post("/projects", {"name": prompt.project_name, "description": f"Created by {MANAGED_BY}."})
        self._projects = None
        outcome.project_id = created["id"]
        self._say(outcome, "project created")
        return str(created["id"])

    def _provider_names(self) -> set[str]:
        if self._providers is None:
            self._providers = {p["name"] for p in self.api.get("/providers")}
        return self._providers

    def _keys(self, project_id: str | None, outcome: Outcome) -> None:
        keys = self.loaded.file.keys
        if not keys:
            return
        stored = self.api.get(f"/projects/{project_id}/credentials") if project_id else []
        existing = {c["provider"]: c for c in stored}
        for provider, reference in keys.items():
            if provider not in self._provider_names():
                raise CliError(
                    f"Verano doesn't know a provider called '{provider}'.",
                    "Providers: " + ", ".join(sorted(self._provider_names())),
                )
            if provider in existing:
                self._rotate_if_changed(project_id, provider, reference, existing[provider], outcome)
                continue
            if self.dry:
                source = "(no key needed)" if reference == "none" else f"key from {reference}"
                self._say(outcome, "", would=f"add {provider}: {source}")
                continue
            match = ENV_REFERENCE.match(reference)
            secret = self.env.get(match.group(1), "").strip() if match and match.group(1) else None
            created = self.api.post(f"/projects/{project_id}/credentials", {"provider": provider, "api_key": secret})
            tail = f" (ends …{created['key_last4']})" if created.get("key_last4") else ""
            what = "key added" if secret else "added (no key needed)"
            self._say(outcome, f"{provider}: {what}{tail}, {created['model_count']} models found")

    def _rotate_if_changed(
        self, project_id: str | None, provider: str, reference: str, stored: dict[str, Any], outcome: Outcome
    ) -> None:
        """A key whose last four characters differ from the stored one has been rotated: replace it in place, so
        the models and settings that use it carry on."""
        match = ENV_REFERENCE.match(reference)
        secret = self.env.get(match.group(1), "").strip() if match and match.group(1) else ""
        if not secret or stored.get("key_last4") in (None, secret[-KEY_TAIL:]):
            self._say(outcome, f"{provider}: key already set")
            return
        if self.dry:
            self._say(outcome, "", would=f"replace the {provider} key (the key in {reference} is a new one)")
            return
        self.api.request("PATCH", f"/projects/{project_id}/credentials/{stored['id']}", json={"api_key": secret})
        self._say(outcome, f"{provider}: key replaced (now ends …{secret[-KEY_TAIL:]}); models and settings kept")

    def _set_label(
        self, project_id: str | None, prompt: ResolvedPrompt, version: dict[str, Any] | None, outcome: Outcome
    ) -> None:
        """Points the label at the version that was just pushed, so an app fetching it gets this text."""
        if self.dry or project_id is None or version is None:
            self._say(outcome, "", would=f"point the label {self.label} at the pushed version")
            return
        found = next(
            (p for p in self.api.pages(f"/projects/{project_id}/prompts") if p["name"] == prompt.entry.name), None
        )
        if found is None:
            return
        self.api.put(f"/projects/{project_id}/prompts/{found['id']}/labels/{self.label}", {"version_id": version["id"]})
        self._say(outcome, f"label {self.label} now points at version {version['version']}")

    def _report_removed(self, existing: list[dict[str, Any]], prompt: ResolvedPrompt, outcome: Outcome) -> None:
        group = prompt.project_name
        wanted = {p.entry.name for p in self.loaded.prompts if p.project_name == group}
        gone = removed_prompts(existing, wanted)
        if gone and self.prune:
            self._delete_removed(existing, gone, outcome)
        elif gone:
            self._say(
                outcome,
                f"no longer in verano.yaml: {', '.join(gone)}. Verano keeps them (and their labels and history); "
                "an app that still fetches them keeps working. Add --prune to delete them.",
            )

    def _delete_removed(self, existing: list[dict[str, Any]], gone: list[str], outcome: Outcome) -> None:
        """`--prune`: delete the prompts this tool made earlier and the file no longer lists, after confirmation.
        A prompt that experiments already used is kept (Verano refuses), and that is said, not treated as a failure."""
        project_id = outcome.project_id
        names = ", ".join(gone)
        if self.dry or project_id is None:
            self._say(outcome, "", would=f"delete the prompts no longer in verano.yaml: {names}")
            return
        if not self.yes:
            if not self.interactive:
                raise CliError(
                    f"Not deleting {names} without your confirmation.",
                    "Add --yes to delete in a script, or leave out --prune to keep them.",
                )
            if not typer.confirm(
                f"Delete {names} from Verano, with all versions and labels? Apps fetching them will stop working.",
                err=True,
            ):
                raise click.exceptions.Abort()
        for prompt in (p for p in existing if p["name"] in gone):
            try:
                self.api.request("DELETE", f"/projects/{project_id}/prompts/{prompt['id']}", params={"confirm": "true"})
            except CliError as error:
                if error.status != HAS_RESULTS_STATUS:
                    raise
                self._say(outcome, f"kept {prompt['name']}: {error.message}")
                continue
            self._say(outcome, f"deleted {prompt['name']}")

    def _models(self, project_id: str | None, prompt: ResolvedPrompt, outcome: Outcome) -> dict[str, Any] | None:
        """Selects the listed models. Returns the judge's profile, if the entry names a judge."""
        entry = prompt.entry
        if project_id is None:
            self._say(outcome, "", would=f"select models: {', '.join(entry.models)}")
            return None
        profiles = self.api.pages(f"/projects/{project_id}/models")
        chosen = [resolve_model(name, profiles) for name in entry.models]
        judge = resolve_model(entry.judge, profiles) if entry.judge else None
        wanted = {p["id"] for p in chosen}
        selected = {p["id"] for p in profiles if p["is_selected"]}
        names = ", ".join(p["display_name"] for p in chosen)
        if selected == wanted:
            self._say(outcome, f"models already selected: {names}")
        elif self.dry:
            self._say(outcome, "", would=f"select models: {names}")
        else:
            self.api.put(
                f"/projects/{project_id}/models/selection",
                {"selected": sorted(wanted - selected), "unselected": sorted(selected - wanted)},
            )
            self._say(outcome, f"models selected: {names}")
        return judge

    def _prompt(self, project_id: str | None, prompt: ResolvedPrompt, outcome: Outcome) -> dict[str, Any] | None:
        """Saves the prompt. Returns its latest version (None when there is nothing to read yet)."""
        entry = prompt.entry
        origin = (
            f" from {entry.source.file}" + (f":{entry.source.line}" if entry.source.line else "")
            if entry.source
            else ""
        )
        reason = f"{MANAGED_BY}{origin}"
        templates = {"system_template": prompt.system, "user_template": prompt.user}
        params = entry.params.given()
        if project_id is None:
            self._say(outcome, "", would="create the prompt (version 1)")
            return None
        existing = self.api.pages(f"/projects/{project_id}/prompts")
        mine = next((p for p in existing if p["name"] == entry.name), None)
        others = [p["name"] for p in existing if p["name"] != entry.name]
        if others and mine is None and not entry.group:
            ui.warn(f"This project also has prompts made elsewhere ({', '.join(others)}). Verano tests the newest one.")
        self._report_removed(existing, prompt, outcome)
        if mine is None:
            if self.dry:
                self._say(outcome, "", would="create the prompt (version 1)")
                return None
            created = self.api.post(
                f"/projects/{project_id}/prompts",
                {"name": entry.name, **templates, "default_params": params, "change_reason": reason},
            )
            self._say(outcome, f"prompt created (version {created['latest_version']['version']})")
            version: dict[str, Any] = created["latest_version"]
            return version
        latest = mine["latest_version"]
        same = (
            normalize_text(latest["system_template"] or "") == (prompt.system or "")
            and normalize_text(latest["user_template"] or "") == (prompt.user or "")
            and latest["default_params"] == params
        )
        if same:
            self._say(outcome, f"prompt unchanged (version {latest['version']})")
            unchanged: dict[str, Any] = latest
            return unchanged
        if self.dry:
            self._say(outcome, "", would=f"save a new prompt version{origin} (now version {latest['version']})")
            return None
        saved = self.api.post(
            f"/projects/{project_id}/prompts/{mine['id']}/versions",
            {**templates, "default_params": params, "change_reason": reason, "parent_version_id": latest["id"]},
        )
        self._say(outcome, f"prompt changed{origin}: saved version {saved['version']}")
        result: dict[str, Any] = saved
        return result


def removed_prompts(existing: list[dict[str, Any]], wanted: set[str]) -> list[str]:
    """Prompts that an earlier push made in this project and the file no longer lists."""
    return sorted(
        p["name"]
        for p in existing
        if p["name"] not in wanted and str(p["latest_version"].get("change_reason") or "").startswith(MANAGED_BY)
    )


def summarize(outcomes: list[Outcome], dry_run: bool) -> None:
    failed = [o for o in outcomes if o.error]
    ui.info("")
    if failed:
        names = ", ".join(o.name for o in failed)
        raise CliError(f"{len(failed)} of {len(outcomes)} prompts could not be pushed: {names}.")
    verb = (
        "Dry run finished; nothing was changed."
        if dry_run
        else f"Pushed {len(outcomes)} prompt{'s' if len(outcomes) != 1 else ''}."
    )
    ui.ok(verb)


def command(
    file: Path | None,
    only: str | None,
    dry_run: bool,
    with_data: bool,
    replace_draft: bool,
    label: str | None = None,
    prune: bool = False,
    yes: bool = False,
) -> None:
    loaded = load(file or find_file())
    pusher = Pusher(
        auth.client(),
        loaded,
        dry_run,
        with_data=with_data,
        replace_draft=replace_draft,
        label=label,
        prune=prune,
        yes=yes,
    )
    summarize(pusher.run(only), dry_run)
