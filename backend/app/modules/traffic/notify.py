"""
Sending an alert: webhook, Slack, email (ADR 0032).

Webhook and Slack addresses are typed by users, so they go through the guarded client (`app/core/egress.py`): private
and internal addresses are refused unless the owner allowed the host, and redirects are not followed. Email is sent
only when the server has SMTP settings. A sender raises `NotifyError` with a message that says what to do.
"""

import asyncio
import smtplib
from collections.abc import Callable
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any, Protocol, TypeVar

import httpx

from app.core.config import Settings
from app.core.egress import EgressPolicy, guarded_request
from app.core.errors import AppError
from app.core.registry import Registry
from app.modules.traffic.domain import compact

NO_EMAIL = (
    "Email is not set up on this server. The owner can set VERANO_TRAFFIC_SMTP_HOST and VERANO_TRAFFIC_SMTP_FROM."
)
SENT_BODY_LIMIT = 65_536


class NotifyError(Exception):
    pass


@dataclass(frozen=True)
class AlertMessage:
    title: str
    text: str
    detail: dict[str, Any]
    alert_id: str
    project_id: str


class Sender(Protocol):
    async def send(
        self, target: str, message: AlertMessage, settings: Settings, transport: httpx.AsyncBaseTransport | None
    ) -> None: ...


SENDERS: Registry[Sender] = Registry("alert channel")
S = TypeVar("S", bound=Sender)


def sender(name: str) -> Callable[[type[S]], type[S]]:
    def decorator(cls: type[S]) -> type[S]:
        SENDERS.add(name, cls())
        return cls

    return decorator


def email_available(settings: Settings) -> bool:
    return bool(settings.traffic_smtp_host and settings.traffic_smtp_from)


async def post_json(
    url: str, payload: dict[str, Any], settings: Settings, transport: httpx.AsyncBaseTransport | None
) -> None:
    policy = EgressPolicy(
        allowed_hosts=frozenset(host.lower() for host in settings.app_allowed_hosts),
        max_bytes=SENT_BODY_LIMIT,
        timeout_s=settings.traffic_alert_timeout_s,
        max_redirects=0,
    )
    try:
        response = await guarded_request(
            "POST",
            url,
            headers={"Content-Type": "application/json"},
            body=compact(payload).encode(),
            policy=policy,
            transport=transport,
        )
    except AppError as error:
        raise NotifyError(error.message) from error
    if response.status >= 300:
        raise NotifyError(f"The address answered with status {response.status}. Check that it is still valid.")


@sender("webhook")
class WebhookSender:
    async def send(
        self, target: str, message: AlertMessage, settings: Settings, transport: httpx.AsyncBaseTransport | None
    ) -> None:
        payload = {
            "event": "verano.alert",
            "title": message.title,
            "text": message.text,
            "alert_id": message.alert_id,
            "project_id": message.project_id,
            "detail": message.detail,
        }
        await post_json(target, payload, settings, transport)


@sender("slack")
class SlackSender:
    async def send(
        self, target: str, message: AlertMessage, settings: Settings, transport: httpx.AsyncBaseTransport | None
    ) -> None:
        await post_json(target, {"text": f"*{message.title}*\n{message.text}"}, settings, transport)


def _send_mail(target: str, message: AlertMessage, settings: Settings) -> None:
    mail = EmailMessage()
    mail["Subject"] = message.title
    mail["From"] = settings.traffic_smtp_from or ""
    mail["To"] = target
    mail.set_content(message.text)
    try:
        with smtplib.SMTP(settings.traffic_smtp_host or "", settings.traffic_smtp_port, timeout=15) as smtp:
            if settings.traffic_smtp_starttls:
                smtp.starttls()
            if settings.traffic_smtp_user:
                smtp.login(settings.traffic_smtp_user, settings.traffic_smtp_password or "")
            smtp.send_message(mail)
    except (OSError, smtplib.SMTPException) as error:
        raise NotifyError(f"The email could not be sent: {error.__class__.__name__}.") from error


@sender("email")
class EmailSender:
    async def send(
        self, target: str, message: AlertMessage, settings: Settings, transport: httpx.AsyncBaseTransport | None
    ) -> None:
        if not email_available(settings):
            raise NotifyError(NO_EMAIL)
        await asyncio.to_thread(_send_mail, target, message, settings)
