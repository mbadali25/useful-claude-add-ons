"""Shared error types for Microsoft Graph callers."""

from __future__ import annotations


class GraphError(RuntimeError):
    """A Microsoft Graph API call failed after retries.

    Carries the HTTP status and Graph's own error code/message - normally
    buried inside the response body as JSON-within-JSON - so a caller gets an
    actionable message instead of a bare status code.
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        request_id: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.request_id = request_id
        detail = f"Graph API error {status_code} ({code}): {message}"
        if request_id:
            detail += f" [request-id: {request_id}]"
        if status_code in (401, 403):
            detail += (
                ". Run this server's doctor entry point to check the token's "
                "tenant, identity, and granted roles/scopes before assuming "
                "the API is at fault."
            )
        super().__init__(detail)


class AuthConfigError(RuntimeError):
    """Required auth environment variables are missing, empty, or contradictory."""
