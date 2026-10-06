"""
The Activity page: how the workspace used models over a period, compared with the period
before. Every project in the user's workspaces counts; nothing is estimated, it is summed from
the recorded model calls.
"""

from collections.abc import Callable
from datetime import UTC, datetime, time

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationFailed
from app.core.security import Principal
from app.modules.activity.domain import key_id, model_name, periods, zone_of
from app.modules.activity.repository import ActivityRepository, as_date
from app.modules.activity.schemas import (
    ActivityKey,
    ActivityOut,
    ActivityProject,
    ActivityQuery,
    ActivityRow,
    FailureCount,
)
from app.modules.auth.service import AuthService

UNKNOWN_ZONE = "Unknown time zone '{name}'. Use a name such as Asia/Kolkata or UTC."


class ActivityService:
    def __init__(self, session: AsyncSession, auth: AuthService, clock: Callable[[], datetime]) -> None:
        self._repo = ActivityRepository(session)
        self._auth = auth
        self._clock = clock

    async def activity(self, principal: Principal, query: ActivityQuery) -> ActivityOut:
        zone = zone_of(query.tz)
        if zone is None:
            raise ValidationFailed(UNKNOWN_ZONE.format(name=query.tz))
        span = periods(self._clock().astimezone(zone).date(), query.days)
        first, after = span.utc_bounds(zone)
        projects = await self._repo.projects(await self._auth.organization_ids(principal.user_id))
        project_ids = [project_id for project_id, _ in projects]
        empty = ActivityOut(
            timezone=query.tz, days=query.days, start=span.start, end=span.end, prior_start=span.prior_start,
            rows=[], projects=[], keys=[], failures=[],
        )  # fmt: skip
        if not project_ids:
            return empty

        credentials = await self._repo.credentials(project_ids)
        key_of = {c.id: key_id(c.provider, c.key_last4) for c in credentials}
        keys: dict[str, ActivityKey] = {}
        for c in credentials:
            entry = keys.setdefault(
                key_of[c.id],
                ActivityKey(id=key_of[c.id], provider=c.provider, last4=c.key_last4, labels=[], projects=0),
            )
            entry.projects += 1
            if c.label and c.label not in entry.labels:
                entry.labels.append(c.label)

        rows = [
            ActivityRow(
                period="current" if as_date(r.day) >= span.start else "prior",
                day=as_date(r.day),
                project_id=r.project_id,
                key=key_of.get(r.credential_id) if r.credential_id else None,
                provider=r.provider,
                model=model_name(r.model),
                purpose=r.purpose,
                requests=r.requests,
                failed=r.failed,
                input_tokens=r.input_tokens,
                output_tokens=r.output_tokens,
                cached_input_tokens=r.cached_input_tokens,
                reasoning_tokens=r.reasoning_tokens,
                input_tokens_with_cache_report=r.input_tokens_with_cache_report,
                cost=r.cost,
                unknown_price_calls=r.unknown_price_calls,
            )
            for r in await self._repo.daily(project_ids, query.tz, first, after)
        ]
        since = datetime.combine(span.start, time.min, zone).astimezone(UTC)
        failures = await self._repo.failures(project_ids, since, after)
        used = {row.project_id for row in rows}
        return empty.model_copy(
            update={
                "rows": sorted(rows, key=lambda row: (row.day, row.model)),
                "projects": [ActivityProject(id=pid, name=name) for pid, name in projects if pid in used],
                "keys": list(keys.values()),
                "failures": [FailureCount(error_type=kind, count=count) for kind, count in failures],
            }
        )
