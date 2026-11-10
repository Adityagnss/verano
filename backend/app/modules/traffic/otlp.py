"""
OTLP over HTTP as protobuf, turned into the JSON the receiver already reads (ADR 0031).

The standard Python exporter (`opentelemetry-exporter-otlp-proto-http`) only speaks protobuf, so a receiver that took
JSON alone could not hear most Python apps. A protobuf request is decoded with the official generated classes and
converted to the OTLP JSON shape (ids as hex text, like the JSON exporters send them), so both forms go through one
path. The reply is protobuf too, as the protocol asks.
"""

import base64
import json
from typing import Any

from google.protobuf.json_format import MessageToDict
from google.protobuf.message import DecodeError
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2 as service

ID_FIELDS = ("traceId", "spanId", "parentSpanId")
PROTOBUF = "application/x-protobuf"


def _hex_ids(item: dict[str, Any]) -> None:
    for key in ID_FIELDS:
        if isinstance(item.get(key), str):
            item[key] = base64.b64decode(item[key]).hex()


def protobuf_to_json(body: bytes) -> bytes:
    """The OTLP JSON for a protobuf export request. Raises ValueError when the bytes are not one."""
    try:
        request = service.ExportTraceServiceRequest.FromString(body)
    except DecodeError as error:
        raise ValueError(str(error)) from error
    data: dict[str, Any] = MessageToDict(request)
    for resource in data.get("resourceSpans", []):
        for scope in resource.get("scopeSpans", []):
            for span in scope.get("spans", []):
                _hex_ids(span)
                for link in span.get("links", []):
                    _hex_ids(link)
    return json.dumps(data).encode()


def protobuf_reply(rejected: int, message: str | None) -> bytes:
    """The export response: empty when everything was taken, else how many spans were not and why."""
    reply = service.ExportTraceServiceResponse()
    if rejected:
        reply.partial_success.rejected_spans = rejected
        reply.partial_success.error_message = message or ""
    out: bytes = reply.SerializeToString()
    return out
