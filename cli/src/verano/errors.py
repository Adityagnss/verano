"""One error type for everything the user can fix; its message is shown as is, without a traceback."""


class CliError(Exception):
    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint
