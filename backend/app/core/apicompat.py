"""
API compatibility (ADR 0022): what a client can rely on in `/api/v1`, and what counts as breaking it.

`signature` reduces an OpenAPI document to what clients depend on: for every route and method, the parameters that
are required, the properties a request must carry, and the properties and status codes a response carries.
`breaking_changes` compares the signature of the last release with the current one and lists every removal or new
requirement. Additions are always fine inside a version. A route marked deprecated is not breaking while it still
exists. Pure code.
"""

from typing import Any

HTTP_METHODS = ("get", "put", "post", "delete", "patch")


def _resolve(spec: dict[str, Any], node: dict[str, Any] | None, depth: int = 0) -> dict[str, Any]:
    """The schema a node points to, following `$ref` (and the first branch of anyOf/allOf), a few levels deep."""
    node = node or {}
    while "$ref" in node and depth < 8:
        target: Any = spec
        for part in node["$ref"].removeprefix("#/").split("/"):
            target = target.get(part, {})
        node, depth = target, depth + 1
    for key in ("allOf", "anyOf", "oneOf"):
        if node.get(key):
            merged: dict[str, Any] = {"properties": {}, "required": []}
            for branch in node[key]:
                resolved = _resolve(spec, branch, depth + 1)
                merged["properties"].update(resolved.get("properties", {}))
                merged["required"] += resolved.get("required", [])
            return merged | {k: v for k, v in node.items() if k not in (key, "properties", "required")}
    return node


def _schema_of(spec: dict[str, Any], content: dict[str, Any] | None) -> dict[str, Any]:
    if not content:
        return {}
    body: dict[str, Any] = content.get("application/json") or next(iter(content.values()), {})
    return _resolve(spec, body.get("schema"))


def _items(spec: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    return _resolve(spec, schema.get("items")) if schema.get("type") == "array" else schema


def signature(spec: dict[str, Any]) -> dict[str, Any]:
    routes: dict[str, Any] = {}
    for path, item in spec.get("paths", {}).items():
        for method in HTTP_METHODS:
            operation = item.get(method)
            if operation is None:
                continue
            required_params = sorted(
                f"{p['in']}:{p['name']}" for p in operation.get("parameters", []) if p.get("required") and "name" in p
            )
            request = _items(spec, _schema_of(spec, (operation.get("requestBody") or {}).get("content")))
            responses = {}
            for code, response in (operation.get("responses") or {}).items():
                shown = _items(spec, _schema_of(spec, response.get("content")))
                responses[code] = sorted(shown.get("properties", {}))
            routes[f"{method.upper()} {path}"] = {
                "deprecated": bool(operation.get("deprecated")),
                "required_params": required_params,
                "request_properties": sorted(request.get("properties", {})),
                "request_required": sorted(request.get("required", [])),
                "responses": responses,
            }
    return routes


def breaking_changes(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    """Every way `new` breaks a client written against `old`, in plain words."""
    problems = []
    for route, was in sorted(old.items()):
        now = new.get(route)
        if now is None:
            if not was["deprecated"]:
                problems.append(f"{route} was removed without being deprecated first.")
            continue
        for param in sorted(set(now["required_params"]) - set(was["required_params"])):
            problems.append(f"{route} now requires the parameter {param}.")
        for name in sorted(set(now["request_required"]) - set(was["request_required"])):
            problems.append(f"{route} now requires the request field {name}.")
        for name in sorted(set(was["request_properties"]) - set(now["request_properties"])):
            problems.append(f"{route} no longer accepts the request field {name}.")
        for code, fields in was["responses"].items():
            if code not in now["responses"]:
                problems.append(f"{route} no longer answers with status {code}.")
                continue
            for name in sorted(set(fields) - set(now["responses"][code])):
                problems.append(f"{route} no longer returns {name} in its {code} response.")
    return problems
