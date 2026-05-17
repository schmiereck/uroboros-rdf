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


class QuotaError(TokenLimitError):
    """Raised when the usage quota is exhausted.

    IS-A TokenLimitError so all existing no-retry guards propagate it correctly.
    Recovery differs from a token limit: wait for quota reset, don't trim context.
    """

    def __init__(self, model_role: str, detail: str = "") -> None:
        self.model = model_role
        self.detail = detail
        msg = f"Usage quota exceeded [{model_role}]"
        if detail:
            msg += f": {detail}"
        # Use Exception.__init__ directly to avoid re-formatting from parent
        Exception.__init__(self, msg)
