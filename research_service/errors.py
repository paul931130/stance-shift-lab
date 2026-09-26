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
