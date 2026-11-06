"""
Outgoing email over SMTP (optional).

With `VERANO_SMTP_HOST` unset nothing is sent and `enabled` is false: callers then show the link on screen
instead (an owner copies an invite link). A send that fails never fails the request; it returns False and the
caller says the email could not be sent. The blocking smtplib call runs in a worker thread. In Docker Compose
the `mail` profile starts a local mail catcher that the settings can point at.
"""

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import Settings

log = logging.getLogger(__name__)


class Mailer:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def enabled(self) -> bool:
        return bool(self._settings.smtp_host)

    async def send(self, to: str, subject: str, body: str) -> bool:
        if not self.enabled:
            return False
        message = EmailMessage()
        message["From"] = self._settings.smtp_from
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        try:
            await asyncio.to_thread(self._deliver, message)
        except (OSError, smtplib.SMTPException) as exc:
            log.warning("email to %s could not be sent: %s", to, exc.__class__.__name__)
            return False
        return True

    def _deliver(self, message: EmailMessage) -> None:
        settings = self._settings
        assert settings.smtp_host is not None
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_s) as smtp:
            if settings.smtp_starttls:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
            smtp.send_message(message)
