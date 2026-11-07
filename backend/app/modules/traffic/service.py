"""
Traffic use cases (ADR 0031): the list, one trace, settings, ingest tokens, numbers, the daily score line and cases
made from traffic.

Cases from traffic are always drafts: they go into the project's draft dataset version through the datasets service,
exactly like generated cases, and nothing in a test set is used until the person approves it there (rule A2.2).
Near-duplicates are folded with the same embedder and similarity as the generator's dedupe, against each other and
against the cases already in the draft.
"""

import asyncio
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import Container
from app.core.errors import NotFound
from app.core.pagination import Page, PageParams, to_page
from app.core.security import Principal, digest_token, utcnow
from app.modules.datasets.schemas import ItemSource, ReviewStatus
from app.modules.datasets.service import DatasetService
from app.modules.evaluation.repository import EvaluatorRepository
from app.modules.generator.domain import case_text
from app.modules.generator.plugins.embedders import build_embedder
from app.modules.projects.schemas import ProjectOut
from app.modules.traffic.config import FIELDS, effective_config, new_row
from app.modules.traffic.domain import fold_duplicates
from app.modules.traffic.ingest import PURGE_JOB, TOKEN_PREFIX
from app.modules.traffic.models import TrafficTrace
from app.modules.traffic.notify import email_available
from app.modules.traffic.repository import TrafficRepository
from app.modules.traffic.schemas import (
    ConfigOut,
    ConfigUpdate,
    DailyScore,
    IngestDayOut,
    MakeCases,
    MakeCasesOut,
    PurgeOut,
    ScoreState,
    TokenCreate,
    TokenCreated,
    TokenOut,
    TraceFilter,
    TraceOut,
    TraceScoreOut,
    TraceStatus,
    TraceSummary,
    TrafficStats,
)

TRACE_NOT_FOUND = "This trace doesn't exist in this project."
TOKEN_NOT_FOUND = "This ingest token doesn't exist in this project."
PREVIEW_CHARS = 300
EMBED_CHARS = 1_000
KNOWN_LIMIT = 2_000
RECENT_DAYS = 14
FROM_TRAFFIC = "from_traffic"


def preview(text: str) -> str:
    return text if len(text) <= PREVIEW_CHARS else text[:PREVIEW_CHARS] + "…"


def summary_of(row: TrafficTrace) -> TraceSummary:
    return TraceSummary(
        id=row.id,
        source=row.source,
        started_at=row.started_at,
        input_preview=preview(row.input_text),
        output_preview=preview(row.output_text),
        status=TraceStatus(row.status),
        latency_ms=row.latency_ms,
        model=row.model,
        prompt_version=row.prompt_version,
        rating=row.rating,
        quality=row.quality,
        passed=row.passed,
        score_state=ScoreState(row.score_state),
        input_truncated=row.input_truncated,
        output_truncated=row.output_truncated,
        scrubbed_count=row.scrubbed_count,
        case_made=row.case_made_at is not None,
    )


def token_out(row: Any) -> TokenOut:
    return TokenOut(
        id=row.id,
        name=row.name,
        prefix=row.prefix,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
    )


class TrafficService:
    def __init__(self, session: AsyncSession, container: Container) -> None:
        self._session = session
        self._container = container
        self._settings = container.settings
        self._repo = TrafficRepository(session)
        self._datasets = DatasetService(session, container.settings)

    # ------------------------------------------------------------------------------------------- settings

    async def config(self, project_id: uuid.UUID) -> ConfigOut:
        return effective_config(await self._repo.config(project_id), self._settings)

    async def update_config(self, project_id: uuid.UUID, body: ConfigUpdate) -> ConfigOut:
        values = effective_config(await self._repo.config(project_id), self._settings).model_dump()
        values.update(body.model_dump(exclude_unset=True, exclude_none=True))
        row = await self._repo.config(project_id)
        if row is None:
            row = new_row(project_id, {name: values[name] for name in FIELDS})
        else:
            for name in FIELDS:
                setattr(row, name, values[name])
        await self._repo.save_config(row)
        return effective_config(row, self._settings)

    # ------------------------------------------------------------------------------------------- tokens

    async def create_token(self, project: ProjectOut, principal: Principal, body: TokenCreate) -> TokenCreated:
        from app.modules.traffic.models import TrafficToken

        raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
        row = TrafficToken(
            project_id=project.id,
            name=body.name.strip(),
            token_hash=digest_token(raw),
            prefix=raw[:12],
            created_by=principal.user_id,
        )
        await self._repo.add(row)
        base = token_out(row)
        return TokenCreated(**base.model_dump(), token=raw, endpoint=f"{self._settings.api_prefix}/otlp/v1/traces")

    async def tokens(self, project_id: uuid.UUID) -> list[TokenOut]:
        return [token_out(row) for row in await self._repo.tokens(project_id)]

    async def revoke_token(self, project_id: uuid.UUID, token_id: uuid.UUID) -> None:
        row = await self._repo.token(project_id, token_id)
        if row is None:
            raise NotFound(TOKEN_NOT_FOUND)
        row.revoked_at = row.revoked_at or utcnow()
        await self._session.flush()

    # ------------------------------------------------------------------------------------------- traces

    async def page(self, project_id: uuid.UUID, where: TraceFilter, page: PageParams) -> Page[TraceSummary]:
        s = self._settings
        rows = await self._repo.page(project_id, where, page, s.traffic_low_rating, s.traffic_long_ms)
        return to_page([summary_of(row) for row in rows], page, lambda item: item.id)

    async def get(self, project_id: uuid.UUID, trace_id: uuid.UUID) -> TraceOut:
        row = await self._repo.trace(project_id, trace_id)
        if row is None:
            raise NotFound(TRACE_NOT_FOUND)
        scores = await self._repo.scores_of(row.id)
        return TraceOut(
            **summary_of(row).model_dump(),
            input_text=row.input_text,
            output_text=row.output_text,
            error_message=row.error_message,
            tokens_in=row.tokens_in,
            tokens_out=row.tokens_out,
            cost=row.cost,
            meta=row.meta,
            scores=[
                TraceScoreOut(
                    evaluator_name=s.evaluator_name, value=s.value, passed=s.passed, judged=s.judged, reason=s.reason
                )
                for s in scores
            ],
        )

    async def delete(self, project_id: uuid.UUID, trace_id: uuid.UUID) -> None:
        if not await self._repo.delete_trace(project_id, trace_id):
            raise NotFound(TRACE_NOT_FOUND)

    # ------------------------------------------------------------------------------------------- numbers

    async def stats(self, project_id: uuid.UUID) -> TrafficStats:
        now = utcnow()
        config = await self.config(project_id)
        counts = await self._repo.counts(project_id)
        days = await self._repo.ingest_days(project_id, (now - timedelta(days=RECENT_DAYS)).date())
        used = await self._repo.judged_since(project_id, datetime(now.year, now.month, 1, tzinfo=now.tzinfo))
        has_checks = await EvaluatorRepository(self._session).project_set(project_id) is not None
        return TrafficStats(
            total=counts["total"],
            by_source=counts["by_source"],
            by_state=counts["by_state"],
            oldest=counts["oldest"],
            newest=counts["newest"],
            retention_days=config.retention_days,
            days=[
                IngestDayOut(
                    day=d.day,
                    accepted=d.accepted,
                    ignored=d.ignored,
                    dropped_rate=d.dropped_rate,
                    dropped_size=d.dropped_size,
                    rejected_requests=d.rejected_requests,
                )
                for d in days
            ],
            dropped_recent=sum(d.dropped_rate + d.dropped_size + d.rejected_requests for d in days),
            judge_used_this_month=used,
            judge_monthly_limit=config.judge_monthly_limit,
            scoring_enabled=config.scoring_enabled,
            has_checks=has_checks,
            email_available=email_available(self._settings),
        )

    async def daily(self, project_id: uuid.UUID, days: int) -> list[DailyScore]:
        since = utcnow() - timedelta(days=days)
        rows = await self._repo.daily(project_id, since)
        return [
            DailyScore(
                day=row.day,
                prompt_version=row.prompt_version,
                traces=int(row.traces),
                errors=int(row.errors),
                scored=int(row.scored),
                passed=int(row.passed),
                pass_rate=int(row.passed) / int(row.scored) if row.scored else None,
                mean_quality=float(row.quality) if row.quality is not None else None,
                judged=int(row.judged),
            )
            for row in rows
        ]

    async def purge(self, project_id: uuid.UUID) -> PurgeOut:
        config = await self.config(project_id)
        cutoff = utcnow() - timedelta(days=config.retention_days)
        return PurgeOut(deleted=await self._repo.purge(project_id, cutoff))

    def schedule_purge(self, project_id: uuid.UUID) -> None:
        self._container.jobs.enqueue(PURGE_JOB, project_id=str(project_id))

    # ------------------------------------------------------------------------------------------- cases

    async def make_cases(self, project: ProjectOut, body: MakeCases) -> MakeCasesOut:
        s = self._settings
        cap = min(body.max_cases, s.traffic_cases_max_select)
        if body.trace_ids:
            chosen = await self._repo.traces(project.id, body.trace_ids[:cap])
            if not chosen:
                raise NotFound(TRACE_NOT_FOUND)
        else:
            assert body.filter is not None
            chosen = await self._repo.select_for_cases(
                project.id, body.filter, cap, s.traffic_low_rating, s.traffic_long_ms
            )
        already = [t for t in chosen if t.case_made_at is not None]
        empty = [t for t in chosen if t.case_made_at is None and not t.input_text.strip()]
        usable = [t for t in chosen if t.case_made_at is None and t.input_text.strip()]
        draft = await self._datasets.find_draft(project.id)
        embedder = build_embedder(s)
        known_texts: list[str] = []
        if draft is not None:
            existing = await self._datasets.items(draft.id)
            known_texts = [case_text(item.inputs)[:EMBED_CHARS] for item in existing[-KNOWN_LIMIT:]]
        texts = [t.input_text[:EMBED_CHARS] for t in usable]
        vectors = await asyncio.to_thread(embedder.embed, [*known_texts, *texts]) if texts else []
        placed = fold_duplicates(vectors[len(known_texts) :], vectors[: len(known_texts)], s.dedupe_similarity)
        keep = [i for i, p in enumerate(placed) if p == -1]
        followers: dict[int, int] = {}
        for p in placed:
            if p >= 0:
                followers[p] = followers.get(p, 0) + 1
        folded = len(usable) - len(keep)
        if body.dry_run or not keep:
            return self._cases_out(None, chosen, len(keep), folded, already, empty, body.dry_run)
        version = await self._datasets.ensure_draft(project.id)
        await self._datasets.inherit_evaluators(project.id, version)
        rows = [
            {
                "inputs": {body.variable: usable[i].input_text},
                "expected_output": None,
                "rubric": None,
                "category": FROM_TRAFFIC,
                "tags": [FROM_TRAFFIC, usable[i].source],
                "source": ItemSource.TRAFFIC,
                "review_status": ReviewStatus.DRAFT,
                "split": None,
                "input_file_id": None,
                "source_row": None,
                "context": [],
                "extra": {
                    "traffic_trace_id": str(usable[i].id),
                    "observed_output": usable[i].output_text[:2_000],
                    "similar_traces_folded": followers.get(i, 0),
                },
            }
            for i in keep
        ]
        await self._datasets.add_items(version.id, rows)
        await self._repo.mark_case_made([usable[i].id for i in keep], utcnow())
        return self._cases_out(version.id, chosen, len(keep), folded, already, empty, False)

    @staticmethod
    def _cases_out(
        version_id: uuid.UUID | None,
        chosen: list[TrafficTrace],
        created: int,
        folded: int,
        already: list[TrafficTrace],
        empty: list[TrafficTrace],
        dry_run: bool,
    ) -> MakeCasesOut:
        if dry_run:
            message = (
                f"{created} draft cases would be made from {len(chosen)} traces; {folded} near-duplicates would be "
                "folded. Nothing was changed."
            )
        elif created:
            message = (
                f"{created} draft cases were added to your test set ({folded} near-duplicates folded). They are not "
                "used until you review and approve them on the Test cases step."
            )
        else:
            message = "No new cases were made: every chosen trace was a repeat, already used or empty."
        return MakeCasesOut(
            dataset_version_id=version_id,
            considered=len(chosen),
            created=created,
            folded=folded,
            already_used=len(already),
            empty=len(empty),
            dry_run=dry_run,
            message=message,
        )
