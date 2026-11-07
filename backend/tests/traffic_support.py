"""Helpers for the traffic integration tests: import a file, make an ingest token, send spans, plant scored traffic."""

import gzip
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select

from app.core.container import Container
from app.core.ids import uuid7
from app.modules.traffic.domain import topic_hash
from app.modules.traffic.models import TrafficTrace
from tests.helpers import Session
from tests.traffic_samples import as_bytes


def tbase(session: Session) -> str:
    return f"/api/v1/projects/{session.project_id}/traffic"


async def import_data(
    client: httpx.AsyncClient,
    session: Session,
    data: Any,
    fmt: str = "auto",
    prompt_version: str | None = None,
    raw: bytes | None = None,
) -> httpx.Response:
    form = {"format": fmt, **({"prompt_version": prompt_version} if prompt_version else {})}
    content = raw if raw is not None else as_bytes(data)
    return await client.post(
        f"{tbase(session)}/import",
        files={"file": ("export.json", content, "application/json")},
        data=form,
        headers=session.headers,
    )


async def traces(client: httpx.AsyncClient, session: Session, **params: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        query = {"limit": 100, **params, **({"cursor": cursor} if cursor else {})}
        page = (await client.get(tbase(session), params=query, headers=session.headers)).json()
        out += page["items"]
        cursor = page.get("next_cursor")
        if not cursor:
            return out


async def make_token(client: httpx.AsyncClient, session: Session, name: str = "prod app") -> dict[str, Any]:
    response = await client.post(f"{tbase(session)}/tokens", json={"name": name}, headers=session.headers)
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def send_spans(
    client: httpx.AsyncClient,
    token: str | None,
    payload: Any,
    *,
    gz: bool = False,
    path: str = "/v1/traces",
    content_type: str = "application/json",
    extra: dict[str, str] | None = None,
    raw: bytes | None = None,
) -> httpx.Response:
    body = raw if raw is not None else json.dumps(payload).encode()
    headers = {"Content-Type": content_type, **(extra or {})}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if gz:
        body = gzip.compress(body)
        headers["Content-Encoding"] = "gzip"
    return await client.post(path, content=body, headers=headers)


async def stats(client: httpx.AsyncClient, session: Session) -> dict[str, Any]:
    body: dict[str, Any] = (await client.get(f"{tbase(session)}/stats", headers=session.headers)).json()
    return body


async def set_config(client: httpx.AsyncClient, session: Session, **values: Any) -> dict[str, Any]:
    response = await client.put(f"{tbase(session)}/config", json=values, headers=session.headers)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def plant(
    container: Container,
    session: Session,
    days: list[tuple[int, int, int]],
    *,
    prompt_version: str | None = "v1",
    scored: bool = True,
) -> None:
    """Scored traffic written straight to the table: `(days_ago, good, total)` per day. Each good trace passed."""
    now = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
    rows = []
    for ago, good, total in days:
        for n in range(total):
            question = f"planted question {ago} {n}"
            rows.append(
                TrafficTrace(
                    id=uuid7(),
                    project_id=session.project_id,
                    source="otlp",
                    external_id=f"planted-{ago}-{n}-{uuid.uuid4().hex[:6]}",
                    started_at=now - timedelta(days=ago, seconds=n),
                    input_text=question,
                    output_text="answer",
                    status="ok",
                    meta={},
                    topic_hash=topic_hash(question),
                    prompt_version=prompt_version,
                    score_state="scored" if scored else "new",
                    passed=(n < good) if scored else None,
                    quality=(1.0 if n < good else 0.0) if scored else None,
                    scored_at=now if scored else None,
                )
            )
    async with container.database.sessions() as db:
        db.add_all(rows)
        await db.commit()


async def trace_rows(container: Container, session: Session) -> list[TrafficTrace]:
    async with container.database.sessions() as db:
        return list((await db.scalars(select(TrafficTrace).where(TrafficTrace.project_id == session.project_id))).all())
