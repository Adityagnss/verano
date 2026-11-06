"""
Langfuse export: a list of traces (or {"data": [...]}), as returned by the Langfuse API or the export in the app.

A trace has an input and an output. Its model, token counts and prompt name come from its generation observations,
and a score named like feedback or rating becomes the person's rating. Errors are traces whose observations have the
level ERROR.
"""

from typing import Any, ClassVar

from app.modules.traffic.domain import (
    ParseResult,
    Problem,
    TraceRecord,
    input_text_of,
    is_feedback_name,
    lookup,
    normalize_rating,
    output_text_of,
    parse_timestamp,
    to_float,
    to_int,
)
from app.modules.traffic.plugins import adapter, records_of


def _observations(trace: dict[str, Any]) -> list[dict[str, Any]]:
    items = trace.get("observations")
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _rating(trace: dict[str, Any]) -> float | None:
    for score in trace.get("scores") or []:
        if isinstance(score, dict) and is_feedback_name(str(score.get("name", ""))):
            rating = normalize_rating(score.get("value"))
            if rating is not None:
                return rating
    return None


@adapter("langfuse")
class LangfuseAdapter:
    name: ClassVar[str] = "langfuse"
    label: ClassVar[str] = "Langfuse"
    hint: ClassVar[str] = "Traces exported from Langfuse as JSON."

    def accepts(self, data: Any) -> bool:
        items = records_of(data, ("data", "traces"))
        sample = [item for item in items[:5] if isinstance(item, dict)]
        return bool(sample) and all(
            ("observations" in item or "totalCost" in item or "latency" in item or "sessionId" in item)
            and "run_type" not in item
            for item in sample
        )

    def parse(self, data: Any, limit: int) -> ParseResult:
        items = records_of(data, ("data", "traces"))
        result = ParseResult(found=len(items))
        for number, trace in enumerate(items[:limit], start=1):
            if not isinstance(trace, dict):
                result.problems.append(Problem(number, "This record is not a Langfuse trace, so it was skipped."))
                continue
            observations = _observations(trace)
            generation = next((o for o in observations if str(o.get("type")).upper() == "GENERATION"), {})
            question = input_text_of(trace.get("input") if trace.get("input") is not None else generation.get("input"))
            answer = output_text_of(
                trace.get("output") if trace.get("output") is not None else generation.get("output")
            )
            if not question.strip() and not answer.strip():
                result.problems.append(Problem(number, "This trace has no input and no output, so it was skipped."))
                continue
            failed = any(str(o.get("level", "")).upper() == "ERROR" for o in observations)
            usage = generation.get("usage") or generation.get("usageDetails") or {}
            latency = to_float(trace.get("latency"))
            meta: dict[str, Any] = {}
            if isinstance(trace.get("metadata"), dict):
                meta.update(trace["metadata"])
            for key in ("name", "release", "environment", "sessionId", "tags"):
                if trace.get(key) not in (None, "", []):
                    meta[key] = trace[key]
            prompt_name = generation.get("promptName")
            prompt_version = generation.get("promptVersion") or trace.get("version")
            result.records.append(
                TraceRecord(
                    external_id=str(trace["id"]) if trace.get("id") else None,
                    started_at=parse_timestamp(trace.get("timestamp") or trace.get("createdAt")),
                    input_text=question,
                    output_text=answer,
                    status="error" if failed else "ok",
                    error_message=str(
                        next((o.get("statusMessage") for o in observations if o.get("statusMessage")), "") or ""
                    )
                    or None
                    if failed
                    else None,
                    latency_ms=round(latency * 1000) if latency is not None else None,
                    model=str(generation.get("model") or "") or None,
                    prompt_version=(f"{prompt_name}@{prompt_version}" if prompt_name else str(prompt_version or ""))
                    or None,
                    rating=_rating(trace),
                    tokens_in=to_int(lookup(usage, "input") or lookup(usage, "promptTokens")),
                    tokens_out=to_int(lookup(usage, "output") or lookup(usage, "completionTokens")),
                    cost=to_float(trace.get("totalCost")),
                    meta=meta,
                )
            )
        return result
