"""Domain exceptions that the API maps to specific HTTP responses.

Only these are translated into client errors. An unexpected KeyError or
TypeError is a bug, so it surfaces as a logged 500 instead of being disguised
as "not found".
"""


class NotFoundError(KeyError):
    """A requested dataset, job or task does not exist (HTTP 404).

    Subclasses KeyError so existing ``except KeyError`` callers keep working.
    """

    def __str__(self):
        # KeyError quotes its argument ('找不到實驗'); show the plain message.
        return str(self.args[0]) if self.args else "找不到指定資源"


class PreflightError(ValueError):
    """A job request fails a named readiness rule (HTTP 422).

    ``reason`` is a stable code the web UI uses to point at the matching
    override checkbox; the message stays human-readable for scripts.
    """

    def __init__(self, reason, message):
        super().__init__(message)
        self.reason = reason
