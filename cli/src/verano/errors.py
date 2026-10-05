"""One error type for everything the user can fix; its message is shown as is, without a traceback."""


class CliError(Exception):
    exit_code = 1

    def __init__(self, message: str, hint: str | None = None, status: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.status = status  # the HTTP status, when the error came from the server


class GateFailed(CliError):
    """The run finished but did not meet the quality gate. Exit code 2, so a pipeline can tell it from an error."""

    exit_code = 2
