"""Resolve per-request Zulip credentials from the OAuth identity.

This replaces the old ``X-Zulip-*`` header source. In OAuth2-only hosted mode
the client presents only its OAuth token; the server derives the user's email
from the validated OAuth claims, then looks up that user's Zulip API key from
the in-memory cache (fast path) or the vault (first contact). If no key is
stored yet, ``EnrollmentRequired`` is raised so the caller can hand back an
enrollment link.
"""

from __future__ import annotations

from ..utils.logging import get_logger
from . import hosted_runtime
from .request_credentials import RequestCredentials
from .secret_store import SecretStoreError

logger = get_logger(__name__)


class EnrollmentRequired(Exception):
    """Raised when an authenticated user has no stored Zulip API key yet."""

    def __init__(self, email: str) -> None:
        super().__init__(f"No Zulip API key on file for {email}")
        self.email = email


class CredentialResolutionUnavailable(Exception):
    """Raised when the vault cannot be reached to resolve a key."""


def oauth_email() -> str | None:
    """Email claim from the validated OAuth access token, if present."""
    from fastmcp.server.dependencies import get_access_token

    try:
        token = get_access_token()
    except Exception:
        return None
    if token is None:
        return None
    claims = token.claims or {}
    email = claims.get("email")
    if not email:
        logger.warning(
            "OAuth token has no 'email' claim (claims present: %s). Request the "
            "email scope (e.g. ZULIPCHAT_AUTH_SCOPES='openid email profile' for "
            "google/oidc) or ensure your IdP puts email in the token.",
            sorted(claims.keys()),
        )
        return None
    return str(email).strip().lower()


async def resolve_request_credentials() -> RequestCredentials | None:
    """Resolve the current request's Zulip credentials from OAuth + vault.

    Returns None when there is no authenticated OAuth identity (e.g. stdio or
    an unauthenticated request). Raises EnrollmentRequired when the user is
    authenticated but has no stored key, and CredentialResolutionUnavailable
    when the vault is unreachable.
    """
    email = oauth_email()
    if not email:
        return None

    cache = hosted_runtime.get_key_cache()
    cached = cache.get(email)
    if cached is not None:
        return RequestCredentials(email=email, api_key=cached)

    store = hosted_runtime.get_secret_store()
    try:
        api_key = await store.get_api_key(email)
    except SecretStoreError as e:
        logger.error("Vault lookup failed for %s: %s", email, e)
        raise CredentialResolutionUnavailable(str(e)) from e

    if api_key is None:
        raise EnrollmentRequired(email)

    cache.set(email, api_key)
    return RequestCredentials(email=email, api_key=api_key)
