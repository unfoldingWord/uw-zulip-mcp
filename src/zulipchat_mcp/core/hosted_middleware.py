"""FastMCP middleware that binds per-request Zulip credentials in hosted mode.

Runs once per tool call:
1. Extracts and validates X-Zulip-* headers (fail-fast, clear errors).
2. In hosted mode, requires them — there is no server-side user fallback.
3. Optionally cross-checks the OAuth identity's email claim against
   X-Zulip-Email (ZULIPCHAT_REQUIRE_EMAIL_MATCH=1), so a user cannot pair
   their own OAuth session with someone else's leaked Zulip key unnoticed.
4. Binds credentials to a contextvar for the duration of the call and
   always unbinds afterwards.
"""

from __future__ import annotations

import os
from typing import Any

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext

from ..utils.logging import get_logger
from .request_credentials import (
    CredentialResolutionError,
    bind_request_credentials,
    is_hosted_mode,
    resolve_credentials_from_headers,
    unbind_request_credentials,
)

logger = get_logger(__name__)

_MISSING_CREDS_MSG = (
    "This server runs in hosted mode: supply your Zulip credentials with "
    "every request via the X-Zulip-Email and X-Zulip-Key HTTP headers. "
    "They are used in-memory for this request only and never stored. "
    "Find your API key in Zulip: Personal settings > Account & privacy."
)


def _require_email_match() -> bool:
    return os.getenv("ZULIPCHAT_REQUIRE_EMAIL_MATCH", "0") in ("1", "true", "True")


def _oauth_email_claim() -> str | None:
    """Email claim from the OAuth access token, when an auth provider is active."""
    from fastmcp.server.dependencies import get_access_token

    try:
        token = get_access_token()
    except Exception:
        return None
    if token is None:
        return None
    claims = token.claims or {}
    email = claims.get("email")
    return str(email) if email else None


class ZulipCredentialMiddleware(Middleware):
    """Resolve and bind per-request Zulip credentials around every tool call."""

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Any],
    ) -> Any:
        try:
            creds = resolve_credentials_from_headers()
        except CredentialResolutionError as e:
            raise ToolError(str(e)) from None

        if creds is None and is_hosted_mode():
            raise ToolError(_MISSING_CREDS_MSG)

        if creds is not None and _require_email_match():
            oauth_email = _oauth_email_claim()
            if oauth_email and oauth_email.lower() != creds.email.lower():
                logger.warning(
                    "Rejected tool call: OAuth identity %s does not match "
                    "X-Zulip-Email %s",
                    oauth_email,
                    creds.email,
                )
                raise ToolError(
                    "X-Zulip-Email does not match the authenticated OAuth "
                    "identity. Use your own Zulip credentials."
                )

        token = bind_request_credentials(creds)
        try:
            return await call_next(context)
        finally:
            unbind_request_credentials(token)
