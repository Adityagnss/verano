"""
Structured JSON logging with secret redaction.

`configure_logging` is called once per process (API and workers). Every record is emitted
as one JSON line, and a filter masks anything matching the configured secret patterns
before it is written, as a second line of defence behind the rule that keys are never
logged at all. LiteLLM's own verbose logging is silenced so it can't echo request headers.
"""

import json
import logging
import re
from datetime import UTC, datetime

from app.core.config import Settings

REDACTED = "[REDACTED]"


class RedactingFilter(logging.Filter):
    def __init__(self, patterns: list[str]) -> None:
        super().__init__()
        self._patterns = [re.compile(pattern) for pattern in patterns]

    def redact(self, text: str) -> str:
        for pattern in self._patterns:
            text = pattern.sub(REDACTED, text)
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self.redact(record.getMessage())
        record.args = None
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(getattr(record, "fields", {}))
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(settings: Settings) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactingFilter(settings.log_redact_patterns))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level)
    for noisy in ("LiteLLM", "litellm", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
