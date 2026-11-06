"""What counts as breaking the API (ADR 0022): removals and new requirements do, additions and deprecated routes
do not.
"""

from typing import Any

from app.core.apicompat import breaking_changes, signature


def spec(**routes: dict[str, Any]) -> dict[str, Any]:
    return {"paths": routes, "components": {"schemas": {}}}


def post(request: list[str], required: list[str], response: list[str], deprecated: bool = False) -> dict[str, Any]:
    body = {"type": "object", "properties": {n: {"type": "string"} for n in request}, "required": required}
    answer = {"type": "object", "properties": {n: {"type": "string"} for n in response}}
    return {
        "post": {
            "deprecated": deprecated,
            "requestBody": {"content": {"application/json": {"schema": body}}},
            "responses": {"200": {"content": {"application/json": {"schema": answer}}}},
        }
    }


OLD = signature(spec(**{"/a": post(["x", "y"], ["x"], ["id", "name"])}))


def test_additions_are_not_breaking() -> None:
    new = signature(spec(**{"/a": post(["x", "y", "z"], ["x"], ["id", "name", "extra"]), "/b": post([], [], [])}))
    assert breaking_changes(OLD, new) == []


def test_removals_and_new_requirements_are_breaking() -> None:
    new = signature(spec(**{"/a": post(["x"], ["x", "y"], ["id"])}))
    found = " ".join(breaking_changes(OLD, new))
    assert "no longer accepts the request field y" in found
    assert "now requires the request field y" in found
    assert "no longer returns name" in found
    assert any("was removed" in p for p in breaking_changes(OLD, signature(spec())))


def test_a_deprecated_route_may_go_but_an_undeprecated_one_may_not() -> None:
    deprecated = signature(spec(**{"/a": post(["x"], ["x"], ["id"], deprecated=True)}))
    assert breaking_changes(deprecated, signature(spec())) == []
