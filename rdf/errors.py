"""Custom exceptions for the RDF framework."""

from __future__ import annotations


class TokenLimitError(Exception):
    """Raised when a model hits its context or output token limit.

    Never retried — the same input would hit the same limit again.
    Propagates to the orchestrator loop for user-controlled pause/resume.
    """

    def __init__(self, model: str, detail: str = "") -> None:
        self.model = model
        self.detail = detail
        msg = f"Token limit reached [{model}]"
        if detail:
            msg += f": {detail}"
        super().__init__(msg)
