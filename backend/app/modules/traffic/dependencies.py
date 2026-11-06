"""FastAPI wiring for traffic: its services, the filter from the query string, and the feature switch."""

from datetime import datetime
from typing import Annotated

from fastapi import Depends, Query

from app.core.container import ContainerDep
from app.core.database import SessionDep
from app.modules.traffic.alerts import AlertService
from app.modules.traffic.ingest import ImportService, ReceiverService
from app.modules.traffic.schemas import TraceFilter
from app.modules.traffic.service import TrafficService

TRAFFIC = "traffic"


def get_traffic_service(session: SessionDep, container: ContainerDep) -> TrafficService:
    return TrafficService(session, container)


def get_import_service(session: SessionDep, container: ContainerDep) -> ImportService:
    return ImportService(session, container)


def get_receiver(session: SessionDep, container: ContainerDep) -> ReceiverService:
    return ReceiverService(session, container)


def get_alert_service(session: SessionDep, container: ContainerDep) -> AlertService:
    return AlertService(session, container)


def trace_filter(
    source: Annotated[str | None, Query()] = None,
    failed: Annotated[bool, Query()] = False,
    low_rated: Annotated[bool, Query()] = False,
    long: Annotated[bool, Query()] = False,
    new_topic: Annotated[bool, Query()] = False,
    unused: Annotated[bool, Query()] = False,
    prompt_version: Annotated[str | None, Query(max_length=100)] = None,
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> TraceFilter:
    return TraceFilter(
        source=source,
        failed=failed,
        low_rated=low_rated,
        long=long,
        new_topic=new_topic,
        unused=unused,
        prompt_version=prompt_version,
        since=since,
        until=until,
        q=q,
    )


TrafficServiceDep = Annotated[TrafficService, Depends(get_traffic_service)]
ImportServiceDep = Annotated[ImportService, Depends(get_import_service)]
ReceiverDep = Annotated[ReceiverService, Depends(get_receiver)]
AlertServiceDep = Annotated[AlertService, Depends(get_alert_service)]
FilterDep = Annotated[TraceFilter, Depends(trace_filter)]
