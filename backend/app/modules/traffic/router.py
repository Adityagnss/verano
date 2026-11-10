"""
Traffic HTTP routes (ADR 0031, ADR 0032).

Project routes (signed-in users): import, list, make cases, settings, ingest tokens, the daily score line and alerts.
The receiver (`POST /v1/traces`) is separate: it is called by the user's instrumented app with an ingest token, not by a
person, and is mounted both at the root (the OTLP default path) and under the API prefix (`/api/v1/otlp/v1/traces`,
which the edge proxy forwards).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, UploadFile, status
from fastapi.responses import JSONResponse, Response

from app.core.container import ContainerDep
from app.core.errors import ValidationFailed
from app.core.features import require_feature
from app.core.pagination import Page, PageDep
from app.core.security import CurrentPrincipal, utcnow
from app.modules.projects.dependencies import ProjectScope
from app.modules.traffic.dependencies import (
    TRAFFIC,
    AlertServiceDep,
    FilterDep,
    ImportServiceDep,
    ReceiverDep,
    TrafficServiceDep,
)
from app.modules.traffic.ingest import (
    AUTO,
    BAD_BODY,
    NOT_JSON_BODY,
    PROCESS_JOB,
    TOO_LARGE_BODY,
    PayloadTooLarge,
    UnsupportedMedia,
    format_choices,
    gunzip_limited,
    read_limited,
)
from app.modules.traffic.otlp import PROTOBUF, protobuf_reply, protobuf_to_json
from app.modules.traffic.repository import TrafficRepository
from app.modules.traffic.schemas import (
    AlertOut,
    ChannelCreate,
    ChannelOut,
    ChannelTestOut,
    ConfigOut,
    ConfigUpdate,
    DailyScore,
    EvaluateOut,
    FormatOut,
    ImportReport,
    MakeCases,
    MakeCasesOut,
    PurgeOut,
    RuleCreate,
    RuleOut,
    ScoringRunOut,
    TokenCreate,
    TokenCreated,
    TokenOut,
    TraceOut,
    TraceSummary,
    TrafficStats,
)

IMPORT_READ_CHUNK = 1 << 20

router = APIRouter(
    prefix="/projects/{project_id}/traffic", tags=["traffic"], dependencies=[Depends(require_feature(TRAFFIC))]
)


@router.get("/formats")
async def formats(project: ProjectScope) -> list[FormatOut]:
    return [FormatOut(name=n, label=label, hint=hint) for n, label, hint in format_choices()]


@router.post("/import", status_code=status.HTTP_201_CREATED)
async def import_traces(
    project: ProjectScope,
    service: ImportServiceDep,
    container: ContainerDep,
    file: Annotated[UploadFile, File()],
    format: Annotated[str, Form()] = AUTO,
    prompt_version: Annotated[str | None, Form(max_length=100)] = None,
) -> ImportReport:
    limit = container.settings.traffic_import_max_bytes
    parts: list[bytes] = []
    size = 0
    while chunk := await file.read(IMPORT_READ_CHUNK):
        size += len(chunk)
        if size > limit:
            return await service.import_file(project.id, None, format, prompt_version)
        parts.append(chunk)
    return await service.import_file(project.id, b"".join(parts), format, prompt_version)


@router.get("")
async def list_traces(
    project: ProjectScope, service: TrafficServiceDep, page: PageDep, where: FilterDep
) -> Page[TraceSummary]:
    return await service.page(project.id, where, page)


@router.post("/cases")
async def make_cases(project: ProjectScope, body: MakeCases, service: TrafficServiceDep) -> MakeCasesOut:
    return await service.make_cases(project, body)


@router.get("/stats")
async def stats(project: ProjectScope, service: TrafficServiceDep) -> TrafficStats:
    return await service.stats(project.id)


@router.get("/daily")
async def daily(
    project: ProjectScope, service: TrafficServiceDep, days: Annotated[int, Query(ge=1, le=180)] = 30
) -> list[DailyScore]:
    return await service.daily(project.id, days)


@router.get("/config")
async def get_config(project: ProjectScope, service: TrafficServiceDep) -> ConfigOut:
    return await service.config(project.id)


@router.put("/config")
async def put_config(project: ProjectScope, body: ConfigUpdate, service: TrafficServiceDep) -> ConfigOut:
    return await service.update_config(project.id, body)


@router.post("/purge")
async def purge_now(project: ProjectScope, service: TrafficServiceDep) -> PurgeOut:
    return await service.purge(project.id)


@router.post("/scoring/run")
async def run_scoring(project: ProjectScope, service: TrafficServiceDep, container: ContainerDep) -> ScoringRunOut:
    config = await service.config(project.id)
    if not config.scoring_enabled:
        return ScoringRunOut(queued=False, message="Turn on online scoring first, then run it.")
    container.jobs.enqueue(PROCESS_JOB, project_id=str(project.id))
    return ScoringRunOut(queued=True, message="Scoring started. New results appear in the chart in a moment.")


@router.get("/tokens")
async def list_tokens(project: ProjectScope, service: TrafficServiceDep) -> list[TokenOut]:
    return await service.tokens(project.id)


@router.post("/tokens", status_code=status.HTTP_201_CREATED)
async def create_token(
    project: ProjectScope, principal: CurrentPrincipal, body: TokenCreate, service: TrafficServiceDep
) -> TokenCreated:
    return await service.create_token(project, principal, body)


@router.delete("/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_token(token_id: uuid.UUID, project: ProjectScope, service: TrafficServiceDep) -> None:
    await service.revoke_token(project.id, token_id)


@router.get("/alerts/channels")
async def list_channels(project: ProjectScope, service: AlertServiceDep) -> list[ChannelOut]:
    return await service.channels(project.id)


@router.post("/alerts/channels", status_code=status.HTTP_201_CREATED)
async def add_channel(project: ProjectScope, body: ChannelCreate, service: AlertServiceDep) -> ChannelOut:
    return await service.add_channel(project.id, body)


@router.post("/alerts/channels/{channel_id}/test")
async def test_channel(channel_id: uuid.UUID, project: ProjectScope, service: AlertServiceDep) -> ChannelTestOut:
    return await service.test_channel(project.id, channel_id)


@router.delete("/alerts/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(channel_id: uuid.UUID, project: ProjectScope, service: AlertServiceDep) -> None:
    await service.delete_channel(project.id, channel_id)


@router.get("/alerts/rules")
async def list_rules(project: ProjectScope, service: AlertServiceDep) -> list[RuleOut]:
    return await service.rules(project.id)


@router.post("/alerts/rules", status_code=status.HTTP_201_CREATED)
async def add_rule(project: ProjectScope, body: RuleCreate, service: AlertServiceDep) -> RuleOut:
    return await service.add_rule(project.id, body)


@router.put("/alerts/rules/{rule_id}")
async def change_rule(rule_id: uuid.UUID, project: ProjectScope, body: RuleCreate, service: AlertServiceDep) -> RuleOut:
    return await service.update_rule(project.id, rule_id, body)


@router.delete("/alerts/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(rule_id: uuid.UUID, project: ProjectScope, service: AlertServiceDep) -> None:
    await service.delete_rule(project.id, rule_id)


@router.post("/alerts/evaluate")
async def evaluate_now(project: ProjectScope, service: AlertServiceDep) -> EvaluateOut:
    return await service.evaluate(project.id)


@router.get("/alerts")
async def list_alerts(project: ProjectScope, service: AlertServiceDep, page: PageDep) -> list[AlertOut]:
    return await service.alerts(project.id, page)


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: uuid.UUID, project: ProjectScope, service: AlertServiceDep) -> AlertOut:
    return await service.resolve(project.id, alert_id)


@router.get("/{trace_id}")
async def get_trace(trace_id: uuid.UUID, project: ProjectScope, service: TrafficServiceDep) -> TraceOut:
    return await service.get(project.id, trace_id)


@router.delete("/{trace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trace(trace_id: uuid.UUID, project: ProjectScope, service: TrafficServiceDep) -> None:
    await service.delete(project.id, trace_id)


# ----------------------------------------------------------------------------------------------- the receiver

otlp_router = APIRouter(tags=["traffic receiver"], dependencies=[Depends(require_feature(TRAFFIC))])


def _bearer(authorization: str | None, token_header: str | None) -> str | None:
    if token_header:
        return token_header.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


@otlp_router.post("/v1/traces")
async def receive_traces(
    request: Request,
    receiver: ReceiverDep,
    container: ContainerDep,
    authorization: Annotated[str | None, Header()] = None,
    x_verano_token: Annotated[str | None, Header()] = None,
    x_verano_prompt_version: Annotated[str | None, Header(max_length=100)] = None,
    content_encoding: Annotated[str | None, Header()] = None,
) -> Response:
    token = await receiver.authenticate(_bearer(authorization, x_verano_token))
    kind = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if kind not in ("application/json", PROTOBUF):
        raise UnsupportedMedia(NOT_JSON_BODY)
    limit = container.settings.traffic_receiver_max_bytes
    declared = request.headers.get("content-length")
    body = (
        None
        if declared and declared.isdigit() and int(declared) > limit
        else await read_limited(request.stream(), limit)
    )
    if body is not None and (content_encoding or "").lower() == "gzip":
        body = gunzip_limited(body, limit)
    if body is None:
        async with container.database.sessions() as session:
            await TrafficRepository(session).add_ingest_counts(token.project_id, utcnow().date(), rejected_requests=1)
            await session.commit()
        raise PayloadTooLarge(TOO_LARGE_BODY.format(limit=limit // 1_000_000))
    if not body.strip():
        raise ValidationFailed("The request body is empty.")
    if kind == PROTOBUF:
        try:
            body = protobuf_to_json(body)
        except ValueError as error:
            raise ValidationFailed(BAD_BODY) from error
    result = await receiver.receive(token, body, (x_verano_prompt_version or "").strip() or None)
    if kind == PROTOBUF:
        return Response(protobuf_reply(result.dropped, result.message), media_type=PROTOBUF)
    return JSONResponse(result.body())
