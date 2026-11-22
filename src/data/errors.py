"""Stable, user-facing error codes for data analysis operations."""
from __future__ import annotations


class DataToolError(Exception):
    """An expected validation or data-operation failure.

    Never use raw pandas tracebacks as model-facing error messages.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}
