"""The errors the library raises. Every message says what happened and what to do."""


class VeranoError(Exception):
    """Base class: catch this to handle anything the library raises."""


class VeranoUnreachable(VeranoError):
    """Verano could not be reached and there is no saved copy of the prompt to fall back on."""


class VeranoRefused(VeranoError):
    """Verano answered but said no (wrong token, unknown prompt or label, revoked token). Not retried, not cached."""

    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.status = status
