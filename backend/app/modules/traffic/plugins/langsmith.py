"""
LangSmith export: runs (a list, or {"runs": [...]}), as returned by the LangSmith API or the export in the app.

Runs are grouped by trace; the top-level run of a trace (no parent) becomes the record, or its first LLM run when the
top-level run has no input and output. The model name comes from the run's metadata, token counts and cost from the
run, and feedback scores (feedback_stats) become the person's rating. A run with an error is a failed trace.
"""

from typing import Any, ClassVar

from app.modules.traffic.domain import (
    ParseResult,
    Problem,
    TraceRecord,
    input_text_of,
    is_feedback_name,
    milliseconds_between,
    normalize_rating,
    output_text_of,
    parse_timestamp,
    to_float,
    to_int,
)
from app.modules.traffic.plugins import adapter, records_of


def _rating(run: dict[str, Any]) -> float | None:
    stats = run.get("feedback_stats")
    if isinstance(stats, dict):
        for name, value in stats.items():
            if is_feedback_name(str(name)) and isinstance(value, dict):
                rating = normalize_rating(value.get("avg"))
                if rating is not None:
                    return rating
    return None


def _record(run: dict[str, Any]) -> TraceRecord | None:
    question, answer = input_text_of(run.get("inputs")), output_text_of(run.get("outputs"))
    if not question.strip() and not answer.strip():
        return None
    extra: dict[str, Any] = run["extra"] if isinstance(run.get("extra"), dict) else {}
    metadata: dict[str, Any] = extra["metadata"] if isinstance(extra.get("metadata"), dict) else {}
    started, ended = parse_timestamp(run.get("start_time")), parse_timestamp(run.get("end_time"))
    error = run.get("error")
    meta: dict[str, Any] = {"name": run.get("name"), "run_type": run.get("run_type")}
    if run.get("tags"):
        meta["tags"] = run["tags"]
    return TraceRecord(
        external_id=str(run["id"]) if run.get("id") else None,
        started_at=started,
        input_text=question,
        output_text=answer,
        status="error" if error else "ok",
        error_message=str(error) if error else None,
        latency_ms=milliseconds_between(started, ended),
        model=str(metadata.get("ls_model_name") or metadata.get("model") or "") or None,
        prompt_version=str(metadata.get("prompt_version") or metadata.get("lc_hub_commit_hash") or "") or None,
        rating=_rating(run),
        tokens_in=to_int(run.get("prompt_tokens")),
        tokens_out=to_int(run.get("completion_tokens")),
        cost=to_float(run.get("total_cost")),
        meta={key: value for key, value in meta.items() if value is not None},
    )


@adapter("langsmith")
class LangSmithAdapter:
    name: ClassVar[str] = "langsmith"
    label: ClassVar[str] = "LangSmith"
    hint: ClassVar[str] = "Runs exported from LangSmith as JSON."

    def accepts(self, data: Any) -> bool:
        items = records_of(data, ("runs", "data"))
        sample = [item for item in items[:5] if isinstance(item, dict)]
        return bool(sample) and all("run_type" in item for item in sample)

    def parse(self, data: Any, limit: int) -> ParseResult:
        items = records_of(data, ("runs", "data"))
        result = ParseResult(found=len(items))
        traces: dict[str, list[tuple[int, dict[str, Any]]]] = {}
        for number, run in enumerate(items[:limit], start=1):
            if not isinstance(run, dict):
                result.problems.append(Problem(number, "This record is not a LangSmith run, so it was skipped."))
                continue
            traces.setdefault(str(run.get("trace_id") or run.get("id") or f"run-{number}"), []).append((number, run))
        for runs in traces.values():
            roots = [pair for pair in runs if not pair[1].get("parent_run_id")]
            llms = [pair for pair in runs if str(pair[1].get("run_type", "")).lower() == "llm"]
            chosen = None
            for _, run in [*roots, *llms]:
                chosen = _record(run)
                if chosen is not None:
                    break
            if chosen is None:
                result.problems.append(Problem(runs[0][0], "This run has no inputs and no outputs, so it was skipped."))
            else:
                result.records.append(chosen)
        return result
