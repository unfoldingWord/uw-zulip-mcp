"""FastMCP middleware that binds per-request Zulip credentials in hosted mode.

OAuth2-only model: the client presents only its OAuth token. This middleware
derives the user's email from the validated OAuth identity, resolves their
Zulip API key from the cache or the vault, and binds it for the duration of
the tool call. If the user has no key stored yet, the call fails with a
one-time enrollment link where they can add it.

Runs once per tool call:
1. Resolve credentials from the OAuth identity (cache → vault).
2. If none are resolvable because no key is stored, return an enrollment link.
3. Bind credentials to a contextvar for the call and always unbind afterwards.
"""

from __future__ import annotations

from typing import Any

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext

from ..utils.logging import get_logger
from . import hosted_config
from .credential_resolver import (
    CredentialResolutionUnavailable,
    EnrollmentRequired,
    resolve_request_credentials,
)
from .enrollment import mint_enrollment_token
from .request_credentials import (
    bind_request_credentials,
    is_hosted_mode,
    unbind_request_credentials,
)

logger = get_logger(__name__)

_NO_IDENTITY_MSG = (
    "This server runs in OAuth2-only hosted mode but no authenticated identity "
    "was found on the request. Ensure the MCP client completed the OAuth login "
    "and that ZULIPCHAT_AUTH_MODE is configured."
)

_VAULT_DOWN_MSG = (
    "Your credentials could not be looked up right now (the secret store is "
    "unavailable). Please try again shortly."
)


def _enrollment_message(email: str) -> str:
    """Build the user-facing message with a one-time enrollment link."""
    token = mint_enrollment_token(email)
    base = hosted_config.public_base_url()
    link = f"{base}/enroll?token={token}" if base else f"/enroll?token={token}"
    return (
        "You have not added your Zulip API key yet. Open this link in your "
        f"browser to add it (valid for a short time):\n\n{link}\n\n"
        "The page explains where to find your API key in Zulip."
    )


class ZulipCredentialMiddleware(Middleware):
    """Resolve and bind per-request Zulip credentials around every tool call."""

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Any],
    ) -> Any:
        try:
            creds = await resolve_request_credentials()
        except EnrollmentRequired as e:
            raise ToolError(_enrollment_message(e.email)) from None
        except CredentialResolutionUnavailable:
            raise ToolError(_VAULT_DOWN_MSG) from None

        if creds is None and is_hosted_mode():
            raise ToolError(_NO_IDENTITY_MSG)

        token = bind_request_credentials(creds)
        try:
            return await call_next(context)
        finally:
            unbind_request_credentials(token)
