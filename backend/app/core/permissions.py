"""
The one permission table (ADR 0029).

Every route of the API maps to exactly one `Action`, and every action has one minimum role. Nothing else in
the code decides who may do what: a single dependency (`projects/access.py`, registered where the routers are
included) looks the request up here before any handler runs, so no router carries its own role checks.

Roles are ordered: viewer < member < admin < owner. A route is matched by its method and its path template
(for example `/projects/{project_id}/credentials`) against `RULES`, first match wins; a route no rule covers
is refused (it fails closed) and `unmapped_paths` lists it so a test and the start-up check can see it.
Tokens with the `read` scope can only use actions that change nothing.
Pure: no I/O, no framework imports.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from fnmatch import fnmatchcase


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


ROLE_RANK = {Role.VIEWER: 0, Role.MEMBER: 1, Role.ADMIN: 2, Role.OWNER: 3}


class TokenScope(StrEnum):
    READ = "read"
    WRITE = "write"


class Action(StrEnum):
    ACCOUNT_READ = "account.read"
    ACCOUNT_WRITE = "account.write"
    READ = "read"
    PREVIEW = "preview"
    WRITE = "write"
    RUN = "run"
    DELETE = "delete"
    MANAGE_KEYS = "keys.manage"
    VIEW_MEMBERS = "members.view"
    MANAGE_MEMBERS = "members.manage"
    VIEW_KEYS = "keys.view"
    VIEW_AUDIT = "audit.view"
    VIEW_GUARDRAILS = "guardrails.view"
    MANAGE_GUARDRAILS = "guardrails.manage"


@dataclass(frozen=True)
class Permission:
    minimum: Role
    changes_data: bool
    wording: str  # finishes "Your role can't ..." in the refusal


PERMISSIONS: dict[Action, Permission] = {
    Action.ACCOUNT_READ: Permission(Role.VIEWER, False, "see your account"),
    Action.ACCOUNT_WRITE: Permission(Role.VIEWER, True, "change your account"),
    Action.READ: Permission(Role.VIEWER, False, "read this"),
    Action.PREVIEW: Permission(Role.VIEWER, False, "preview this"),
    Action.WRITE: Permission(Role.MEMBER, True, "change things in this project"),
    Action.RUN: Permission(Role.MEMBER, True, "start or stop runs"),
    Action.DELETE: Permission(Role.MEMBER, True, "delete things"),
    Action.MANAGE_KEYS: Permission(Role.ADMIN, True, "add, change or remove keys"),
    Action.VIEW_MEMBERS: Permission(Role.VIEWER, False, "see the members"),
    Action.MANAGE_MEMBERS: Permission(Role.ADMIN, True, "manage members and invites"),
    Action.VIEW_KEYS: Permission(Role.MEMBER, False, "see the workspace keys"),
    Action.VIEW_AUDIT: Permission(Role.ADMIN, False, "see the audit log"),
    Action.VIEW_GUARDRAILS: Permission(Role.MEMBER, False, "see the spending limit"),
    Action.MANAGE_GUARDRAILS: Permission(Role.ADMIN, True, "change the spending limit"),
}

READ_METHODS = frozenset({"GET", "HEAD"})
ANY = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"})
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH"})


@dataclass(frozen=True)
class Rule:
    """`action` None means the route is public (no sign-in). `by_method` means: GET reads, POST/PUT/PATCH write,
    DELETE deletes, for the project's ordinary routes."""

    methods: frozenset[str]
    pattern: str
    action: Action | None
    by_method: bool = False


def _rule(methods: Iterable[str] | str, pattern: str, action: Action | None, by_method: bool = False) -> Rule:
    chosen = ANY if methods == "*" else frozenset([methods] if isinstance(methods, str) else methods)
    return Rule(chosen, pattern, action, by_method)


PROJ = "/projects/{project_id}"
ORG = "/organizations/{organization_id}"

# Order matters: the first rule that matches wins, so exceptions come before the general rule of their area.
RULES: tuple[Rule, ...] = (
    # public: sign-in, sign-up, the sign-in providers, and looking at an invite link
    _rule("*", "/auth/config", None),
    _rule("POST", "/auth/login", None),
    _rule("POST", "/auth/signup", None),
    _rule("*", "/auth/refresh", None),
    _rule("GET", "/auth/oidc/*", None),
    _rule("POST", "/auth/verify-email", None),
    _rule("GET", "/auth/invites/{token}", None),
    # your own account
    _rule("GET", "/auth/*", Action.ACCOUNT_READ),
    _rule(WRITE_METHODS | {"DELETE"}, "/auth/*", Action.ACCOUNT_WRITE),
    _rule("GET", "/providers", Action.ACCOUNT_READ),
    _rule("GET", "/provider-health", Action.ACCOUNT_READ),
    _rule("POST", "/otlp/v1/traces", None),  # called by the user's app with an ingest token, not by a person
    _rule("GET", "/prompt-notes", Action.ACCOUNT_READ),
    _rule("GET", "/activity", Action.ACCOUNT_READ),
    _rule("GET", "/projects", Action.ACCOUNT_READ),
    _rule("POST", "/projects", Action.ACCOUNT_WRITE),
    # one workspace: people, invites, shared keys, spending limit, audit log
    _rule("GET", f"{ORG}/members*", Action.VIEW_MEMBERS),
    _rule(ANY, f"{ORG}/members*", Action.MANAGE_MEMBERS),
    _rule(ANY, f"{ORG}/invites*", Action.MANAGE_MEMBERS),
    _rule("GET", f"{ORG}/keys*", Action.VIEW_KEYS),
    _rule(ANY, f"{ORG}/keys*", Action.MANAGE_KEYS),
    _rule("GET", f"{ORG}/audit-log*", Action.VIEW_AUDIT),
    _rule("GET", f"{ORG}/guardrails", Action.VIEW_GUARDRAILS),
    _rule(ANY, f"{ORG}/guardrails", Action.MANAGE_GUARDRAILS),
    # one project: keys first, then things that only look, then things that run, then everything else
    _rule("GET", f"{PROJ}/credentials*", Action.READ),
    _rule(ANY, f"{PROJ}/credentials*", Action.MANAGE_KEYS),
    _rule("POST", f"{PROJ}/*/estimate", Action.PREVIEW),
    _rule("POST", f"{PROJ}/prompts/inspect", Action.PREVIEW),
    _rule("POST", f"{PROJ}/prompt-versions/*/render", Action.PREVIEW),
    _rule("POST", f"{PROJ}/prompt-versions/*/check", Action.PREVIEW),
    _rule("POST", f"{PROJ}/experiments", Action.RUN),
    _rule("POST", f"{PROJ}/experiments/*/rerun", Action.RUN),
    _rule("POST", f"{PROJ}/experiments/*/rescore", Action.RUN),
    _rule("POST", f"{PROJ}/experiments/*/judge/try", Action.RUN),
    _rule("POST", f"{PROJ}/experiments/*/cancel", Action.RUN),
    _rule("POST", f"{PROJ}/generations", Action.RUN),
    _rule("POST", f"{PROJ}/dataset-versions/*/regenerate", Action.RUN),
    _rule("POST", f"{PROJ}/dataset-versions/*/generation/cancel", Action.RUN),
    _rule("POST", f"{PROJ}/improvements", Action.RUN),
    _rule("POST", f"{PROJ}/improvements/*/continue", Action.RUN),
    _rule("POST", f"{PROJ}/improvements/*/stop", Action.RUN),
    _rule("POST", f"{PROJ}/llm-calls", Action.RUN),
    _rule("POST", f"{PROJ}/apps/*/test", Action.RUN),
    _rule(ANY, f"{PROJ}", None, by_method=True),
    _rule(ANY, f"{PROJ}/*", None, by_method=True),
)

_BY_METHOD = {"GET": Action.READ, "HEAD": Action.READ, "POST": Action.WRITE, "PUT": Action.WRITE}
_BY_METHOD |= {"PATCH": Action.WRITE, "DELETE": Action.DELETE}


class UnmappedRoute(LookupError):
    """No rule covers this route, so it is refused until someone decides who may use it."""


def _matches(pattern: str, path: str) -> bool:
    return fnmatchcase(path, pattern)


def permission_action(method: str, template: str) -> Action | None:
    """The action a request needs, or None for a public route. Raises `UnmappedRoute` when no rule covers it."""
    verb = method.upper()
    for rule in RULES:
        if verb in rule.methods and _matches(rule.pattern, template):
            if rule.by_method:
                return _BY_METHOD[verb]
            return rule.action
    raise UnmappedRoute(f"{verb} {template}")


def required_role(method: str, template: str) -> Role | None:
    """The lowest role that may call this route; None when anyone may (a public route). Test-friendly entry
    point: `required_role("POST", "/projects/{project_id}/experiments")` is `Role.MEMBER`."""
    action = permission_action(method, template)
    return None if action is None else PERMISSIONS[action].minimum


def role_allows(role: Role, action: Action) -> bool:
    return ROLE_RANK[role] >= ROLE_RANK[PERMISSIONS[action].minimum]


def scope_allows(scope: TokenScope, action: Action) -> bool:
    """A read-only token may only use actions that change nothing."""
    return scope is TokenScope.WRITE or not PERMISSIONS[action].changes_data


def outranks(actor: Role, target: Role) -> bool:
    """Whether `actor` may hand out or take away `target`: owners can do anything; an admin only manages members
    and viewers."""
    if actor is Role.OWNER:
        return True
    return actor is Role.ADMIN and ROLE_RANK[target] <= ROLE_RANK[Role.MEMBER]


def unmapped_paths(operations: Iterable[tuple[str, str]]) -> list[str]:
    """`METHOD path` for every (method, path template) pair that no rule covers."""
    missing = []
    for method, template in operations:
        try:
            permission_action(method, template)
        except UnmappedRoute:
            missing.append(f"{method.upper()} {template}")
    return sorted(missing)
