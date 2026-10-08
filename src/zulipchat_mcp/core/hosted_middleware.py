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
from . import hosted_config, hosted_runtime
from .credential_resolver import (
    CredentialResolutionUnavailable,
    EnrollmentRequired,
    IdentityNotAllowed,
    resolve_request_credentials,
)
from .enrollment import mint_enrollment_token
from .request_credentials import (
    AuthFailureSignal,
    bind_auth_failure_signal,
    bind_request_credentials,
    is_hosted_mode,
    unbind_auth_failure_signal,
    unbind_request_credentials,
)
from .secret_store import SecretStoreError

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

_NOT_ALLOWED_MSG = (
    "Your account is not authorized to use this server. If you believe this is "
    "a mistake, contact your administrator."
)


async def _handle_rotated_key(email: str) -> None:
    """Clear a rejected key so the next call forces re-enrollment.

    Invalidates the in-memory cache and deletes the vault secret. Both must go:
    leaving the (now invalid) key in the vault would just have the resolver
    re-fetch and re-cache it, looping on the same 401.
    """
    hosted_runtime.get_key_cache().invalidate(email)
    try:
        await hosted_runtime.get_secret_store().delete_api_key(email)
    except SecretStoreError as e:
        # Cache is already cleared; log and still prompt re-enrollment. A stale
        # key left in the vault will trip this path again on the next call.
        logger.error("Failed to delete rotated key for %s: %s", email, e)
    logger.info("Zulip rejected stored key for %s; cleared it and re-enrolling", email)


def _enrollment_link(email: str) -> str:
    """A one-time, signed enrollment link for ``email``."""
    token = mint_enrollment_token(email)
    base = hosted_config.public_base_url()
    return f"{base}/enroll?token={token}" if base else f"/enroll?token={token}"


def _enrollment_message(email: str) -> str:
    """Message for a user who has not stored a Zulip API key yet."""
    return (
        "You have not added your Zulip API key yet. Open this link in your "
        f"browser to add it (valid for a short time):\n\n{_enrollment_link(email)}\n\n"
        "The page explains where to find your API key in Zulip."
    )


def _reenrollment_message(email: str) -> str:
    """Message for a user whose stored key Zulip just rejected (rotated/revoked)."""
    return (
        "Your saved Zulip API key is no longer valid — it looks like it was "
        "rotated or revoked in Zulip. Open this link to add your new key "
        f"(valid for a short time):\n\n{_enrollment_link(email)}\n\n"
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
        except IdentityNotAllowed as e:
            logger.warning("Rejected identity not on allowlist: %s", e.email)
            raise ToolError(_NOT_ALLOWED_MSG) from None
        except EnrollmentRequired as e:
            raise ToolError(_enrollment_message(e.email)) from None
        except CredentialResolutionUnavailable:
            raise ToolError(_VAULT_DOWN_MSG) from None

        if creds is None and is_hosted_mode():
            raise ToolError(_NO_IDENTITY_MSG)

        # Per-request signal the Zulip client trips if it hits an auth rejection
        # (the user rotated/revoked their key). Only user clients watch it.
        signal = AuthFailureSignal() if creds is not None else None
        cred_token = bind_request_credentials(creds)
        sig_token = bind_auth_failure_signal(signal)
        try:
            result = await call_next(context)
        finally:
            unbind_auth_failure_signal(sig_token)
            unbind_request_credentials(cred_token)

        if (
            signal is not None
            and signal.triggered
            and creds is not None
            and hosted_config.reenroll_on_auth_failure()
        ):
            await _handle_rotated_key(creds.email)
            raise ToolError(_reenrollment_message(creds.email)) from None

        return result
