"""
Alerts on live traffic (ADR 0032): channels, rules, incidents.

A rule watches the daily pass rate (or success rate) of live traffic. `drift_verdict` (pure, in domain.py) decides
whether it is clearly below the line: a rolling window, a sequential test, and at least a set number of bad days, so one
bad day never alerts. A rule has at most one open incident; it is resolved when the rate recovers, and a new alert is
raised only for a new incident. Notifications wait while the rule's quiet hours last. Failed sends are recorded on
the alert and the channel, never raised.
"""

import uuid
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlsplit

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import Container
from app.core.errors import NotFound, ValidationFailed
from app.core.pagination import PageParams
from app.core.security import utcnow
from app.modules.traffic.domain import DayPoint, drift_verdict, in_quiet_hours
from app.modules.traffic.models import Alert, AlertChannel, AlertRule
from app.modules.traffic.notify import SENDERS, AlertMessage, NotifyError, email_available
from app.modules.traffic.repository import TrafficRepository
from app.modules.traffic.schemas import (
    AlertOut,
    AlertStatus,
    ChannelCreate,
    ChannelKind,
    ChannelOut,
    ChannelTestOut,
    EvaluateOut,
    RuleCreate,
    RuleOut,
)

NO_CHANNEL = "This channel doesn't exist in this project."
NO_RULE = "This alert rule doesn't exist in this project."
NO_ALERT = "This alert doesn't exist in this project."
NO_EMAIL_SETUP = (
    "Email alerts need an email server. The owner can set VERANO_TRAFFIC_SMTP_HOST and VERANO_TRAFFIC_SMTP_FROM."
)
UNKNOWN_CHANNELS = "One of the chosen channels doesn't exist in this project."
LABELS = {"pass_rate": "pass rate", "success_rate": "success rate"}


def hint_of(kind: ChannelKind, target: str) -> str:
    if kind is ChannelKind.EMAIL:
        name, _, domain = target.partition("@")
        return f"{name[:1]}***@{domain}"
    parts = urlsplit(target)
    return f"{parts.netloc}/…" if parts.path.strip("/") else parts.netloc


def channel_out(row: AlertChannel) -> ChannelOut:
    return ChannelOut(
        id=row.id,
        kind=ChannelKind(row.kind),
        name=row.name,
        target_hint=row.target_hint,
        last_error=row.last_error,
        last_sent_at=row.last_sent_at,
    )


def rule_out(row: AlertRule, open_id: uuid.UUID | None) -> RuleOut:
    return RuleOut(
        id=row.id,
        created_at=row.created_at,
        open_alert_id=open_id,
        name=row.name,
        kind=row.kind,
        metric=row.metric,
        threshold=row.threshold,
        margin=row.margin,
        window_days=row.window_days,
        baseline_days=row.baseline_days,
        min_samples=row.min_samples,
        min_bad_days=row.min_bad_days,
        channel_ids=[uuid.UUID(str(c)) for c in row.channel_ids],
        quiet_start_hour=row.quiet_start_hour,
        quiet_end_hour=row.quiet_end_hour,
        quiet_utc_offset_min=row.quiet_utc_offset_min,
        enabled=row.enabled,
    )


def alert_out(row: Alert, rule_name: str) -> AlertOut:
    return AlertOut(
        id=row.id,
        rule_id=row.rule_id,
        rule_name=rule_name,
        status=AlertStatus(row.status),
        title=row.title,
        detail=row.detail,
        created_at=row.created_at,
        resolved_at=row.resolved_at,
        notified_at=row.notified_at,
        notify_results=[r for r in row.notify_results if isinstance(r, dict)],
    )


class AlertService:
    def __init__(
        self, session: AsyncSession, container: Container, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._session = session
        self._settings = container.settings
        self._secrets = container.secret_box
        self._repo = TrafficRepository(session)
        self._transport = transport

    # ------------------------------------------------------------------------------------------- channels

    async def add_channel(self, project_id: uuid.UUID, body: ChannelCreate) -> ChannelOut:
        if body.kind is ChannelKind.EMAIL and not email_available(self._settings):
            raise ValidationFailed(NO_EMAIL_SETUP)
        row = AlertChannel(
            project_id=project_id,
            kind=body.kind.value,
            name=body.name.strip(),
            target_secret=self._secrets.encrypt(body.target),
            target_hint=hint_of(body.kind, body.target),
        )
        await self._repo.add(row)
        return channel_out(row)

    async def channels(self, project_id: uuid.UUID) -> list[ChannelOut]:
        return [channel_out(row) for row in await self._repo.channels(project_id)]

    async def delete_channel(self, project_id: uuid.UUID, channel_id: uuid.UUID) -> None:
        row = await self._channel(project_id, channel_id)
        for rule in await self._repo.rules(project_id):
            if str(channel_id) in [str(c) for c in rule.channel_ids]:
                rule.channel_ids = [c for c in rule.channel_ids if str(c) != str(channel_id)]
        await self._repo.delete_row(row)

    async def test_channel(self, project_id: uuid.UUID, channel_id: uuid.UUID) -> ChannelTestOut:
        row = await self._channel(project_id, channel_id)
        message = AlertMessage(
            "Verano test alert",
            "This is a test. If you can read it, alerts from this project will reach this channel.",
            {"test": True},
            str(uuid.UUID(int=0)),
            str(project_id),
        )
        error = await self._send(row, message)
        return ChannelTestOut(ok=error is None, message=error or "The test alert was sent.")

    async def _channel(self, project_id: uuid.UUID, channel_id: uuid.UUID) -> AlertChannel:
        row = await self._repo.channel(project_id, channel_id)
        if row is None:
            raise NotFound(NO_CHANNEL)
        return row

    async def _send(self, channel: AlertChannel, message: AlertMessage) -> str | None:
        """Sends to one channel; returns what went wrong in words, or None."""
        try:
            await SENDERS[channel.kind].send(
                self._secrets.decrypt(channel.target_secret), message, self._settings, self._transport
            )
        except NotifyError as error:
            channel.last_error = str(error)
            return str(error)
        channel.last_error = None
        channel.last_sent_at = utcnow()
        return None

    # ------------------------------------------------------------------------------------------- rules

    async def _check_channels(self, project_id: uuid.UUID, ids: list[uuid.UUID]) -> None:
        if ids and len(await self._repo.channels_by_ids(project_id, ids)) != len(set(ids)):
            raise ValidationFailed(UNKNOWN_CHANNELS)

    async def add_rule(self, project_id: uuid.UUID, body: RuleCreate) -> RuleOut:
        await self._check_channels(project_id, body.channel_ids)
        row = AlertRule(project_id=project_id, **self._values(body))
        await self._repo.add(row)
        return rule_out(row, None)

    async def update_rule(self, project_id: uuid.UUID, rule_id: uuid.UUID, body: RuleCreate) -> RuleOut:
        row = await self._rule(project_id, rule_id)
        await self._check_channels(project_id, body.channel_ids)
        for name, value in self._values(body).items():
            setattr(row, name, value)
        await self._session.flush()
        return rule_out(row, (await self._repo.open_alert_ids(project_id)).get(row.id))

    @staticmethod
    def _values(body: RuleCreate) -> dict[str, Any]:
        values = body.model_dump(mode="json")
        values["name"] = body.name.strip()
        values["channel_ids"] = [str(c) for c in body.channel_ids]
        return values

    async def rules(self, project_id: uuid.UUID) -> list[RuleOut]:
        open_ids = await self._repo.open_alert_ids(project_id)
        return [rule_out(row, open_ids.get(row.id)) for row in await self._repo.rules(project_id)]

    async def delete_rule(self, project_id: uuid.UUID, rule_id: uuid.UUID) -> None:
        await self._repo.delete_row(await self._rule(project_id, rule_id))

    async def _rule(self, project_id: uuid.UUID, rule_id: uuid.UUID) -> AlertRule:
        row = await self._repo.rule(project_id, rule_id)
        if row is None:
            raise NotFound(NO_RULE)
        return row

    # ------------------------------------------------------------------------------------------- incidents

    async def alerts(self, project_id: uuid.UUID, page: PageParams) -> list[AlertOut]:
        return [alert_out(alert, name) for alert, name in await self._repo.alerts(project_id, page)]

    async def resolve(self, project_id: uuid.UUID, alert_id: uuid.UUID) -> AlertOut:
        row = await self._repo.alert(project_id, alert_id)
        if row is None:
            raise NotFound(NO_ALERT)
        if row.status == "open":
            row.status = "resolved"
            row.resolved_at = utcnow()
            await self._session.flush()
        rule = await self._repo.rule(project_id, row.rule_id)
        return alert_out(row, rule.name if rule else "")

    async def evaluate(self, project_id: uuid.UUID, today: date | None = None) -> EvaluateOut:
        """Checks every enabled rule, opens or resolves incidents, then sends the notifications that are due."""
        now = utcnow()
        today = today or now.date()
        opened = resolved = 0
        open_by_rule = await self._repo.open_alert_ids(project_id)
        series: dict[str, list[DayPoint]] = {}
        for rule in await self._repo.rules(project_id, enabled_only=True):
            if rule.metric not in series:
                since = now - timedelta(days=125)
                rows = await self._repo.day_points(project_id, rule.metric, since)
                series[rule.metric] = [DayPoint(day, good, total) for day, good, total in rows]
            verdict = drift_verdict(
                series[rule.metric],
                kind=rule.kind,
                today=today,
                threshold=rule.threshold,
                margin=rule.margin,
                window_days=rule.window_days,
                baseline_days=rule.baseline_days,
                min_samples=rule.min_samples,
                min_bad_days=rule.min_bad_days,
            )
            if verdict.breached and rule.id not in open_by_rule:
                label = LABELS.get(rule.metric, rule.metric)
                alert = Alert(
                    project_id=project_id,
                    rule_id=rule.id,
                    status="open",
                    title=f"{rule.name}: the {label} of live traffic dropped",
                    detail={
                        "reason": verdict.reason,
                        "line": verdict.reference,
                        "window_rate": verdict.window_rate,
                        "window_traces": verdict.window_total,
                        "bad_days": verdict.bad_days,
                        "evidence": verdict.llr,
                        "metric": rule.metric,
                    },
                    notify_results=[],
                )
                try:
                    async with self._session.begin_nested():
                        await self._repo.add(alert)
                except IntegrityError:
                    continue
                open_by_rule[rule.id] = alert.id
                opened += 1
            elif verdict.recovered and rule.id in open_by_rule:
                row = await self._repo.alert(project_id, open_by_rule.pop(rule.id))
                if row is not None:
                    row.status = "resolved"
                    row.resolved_at = now
                    resolved += 1
        notified = await self._notify_due(project_id)
        return EvaluateOut(opened=opened, resolved=resolved, notified=notified)

    async def _notify_due(self, project_id: uuid.UUID) -> int:
        now = utcnow()
        sent = 0
        rules = {rule.id: rule for rule in await self._repo.rules(project_id)}
        for alert in await self._repo.unnotified(project_id):
            rule = rules.get(alert.rule_id)
            if rule is None:
                continue
            if in_quiet_hours(now, rule.quiet_start_hour, rule.quiet_end_hour, rule.quiet_utc_offset_min):
                continue
            ids = [uuid.UUID(str(c)) for c in rule.channel_ids]
            channels = await self._repo.channels_by_ids(project_id, ids) if ids else []
            message = AlertMessage(
                alert.title, str(alert.detail.get("reason", "")), alert.detail, str(alert.id), str(project_id)
            )
            results = []
            for channel in channels:
                error = await self._send(channel, message)
                results.append({"channel": channel.name, "ok": error is None, "error": error})
            alert.notify_results = results
            alert.notified_at = now
            sent += 1
        return sent
