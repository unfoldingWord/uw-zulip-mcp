"""OAuth 2.1 auth provider factory for the user → MCP server hop.

Env-driven so deployments pick a provider without code changes:

    ZULIPCHAT_AUTH_MODE=none     No auth (default; local/stdio use)
    ZULIPCHAT_AUTH_MODE=jwt      Verify bearer JWTs from an external IdP
        ZULIPCHAT_AUTH_JWKS_URI      JWKS endpoint
        ZULIPCHAT_AUTH_ISSUER        Expected issuer
        ZULIPCHAT_AUTH_AUDIENCE      Expected audience (optional)
    ZULIPCHAT_AUTH_MODE=google   Full OAuth via Google (Workspace orgs)
        ZULIPCHAT_AUTH_CLIENT_ID     Google OAuth client ID
        ZULIPCHAT_AUTH_CLIENT_SECRET Google OAuth client secret
        ZULIPCHAT_AUTH_BASE_URL      Public URL of this MCP server
    ZULIPCHAT_AUTH_MODE=oidc     Any OIDC provider (generic proxy)
        ZULIPCHAT_AUTH_CONFIG_URL    OIDC discovery document URL
        ZULIPCHAT_AUTH_CLIENT_ID / ZULIPCHAT_AUTH_CLIENT_SECRET
        ZULIPCHAT_AUTH_BASE_URL      Public URL of this MCP server
    ZULIPCHAT_AUTH_MODE=static   Fixed bearer tokens — DEV/TEST ONLY
        ZULIPCHAT_AUTH_STATIC_TOKENS Comma-separated tokens

This hop answers "may you talk to this server at all" and provides the
audited user identity. Zulip authorization is separate: the per-request
X-Zulip-* credentials (see request_credentials.py).
"""

from __future__ import annotations

import os

from fastmcp.server.auth import AuthProvider

from ..utils.logging import get_logger

logger = get_logger(__name__)


class AuthConfigurationError(ValueError):
    """Raised when ZULIPCHAT_AUTH_* configuration is incomplete or invalid."""


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise AuthConfigurationError(
            f"{name} is required for ZULIPCHAT_AUTH_MODE="
            f"{os.getenv('ZULIPCHAT_AUTH_MODE')}"
        )
    return value


def build_auth_provider() -> AuthProvider | None:
    """Build the FastMCP auth provider from ZULIPCHAT_AUTH_* env config.

    Returns None when auth is disabled (ZULIPCHAT_AUTH_MODE unset/none).
    Raises AuthConfigurationError on incomplete configuration — a hosted
    server must fail to start rather than start unauthenticated by accident.
    """
    mode = os.getenv("ZULIPCHAT_AUTH_MODE", "none").strip().lower()

    if mode in ("", "none"):
        return None

    if mode == "jwt":
        from fastmcp.server.auth import JWTVerifier

        audience = os.getenv("ZULIPCHAT_AUTH_AUDIENCE", "").strip() or None
        return JWTVerifier(
            jwks_uri=_require("ZULIPCHAT_AUTH_JWKS_URI"),
            issuer=_require("ZULIPCHAT_AUTH_ISSUER"),
            audience=audience,
        )

    if mode == "google":
        from fastmcp.server.auth.providers.google import GoogleProvider

        return GoogleProvider(
            client_id=_require("ZULIPCHAT_AUTH_CLIENT_ID"),
            client_secret=_require("ZULIPCHAT_AUTH_CLIENT_SECRET"),
            base_url=_require("ZULIPCHAT_AUTH_BASE_URL"),
        )

    if mode == "oidc":
        from fastmcp.server.auth import OIDCProxy

        return OIDCProxy(
            config_url=_require("ZULIPCHAT_AUTH_CONFIG_URL"),
            client_id=_require("ZULIPCHAT_AUTH_CLIENT_ID"),
            client_secret=_require("ZULIPCHAT_AUTH_CLIENT_SECRET"),
            base_url=_require("ZULIPCHAT_AUTH_BASE_URL"),
        )

    if mode == "static":
        from fastmcp.server.auth import StaticTokenVerifier

        tokens = [
            t.strip()
            for t in _require("ZULIPCHAT_AUTH_STATIC_TOKENS").split(",")
            if t.strip()
        ]
        if not tokens:
            raise AuthConfigurationError(
                "ZULIPCHAT_AUTH_STATIC_TOKENS contained no tokens"
            )
        logger.warning(
            "ZULIPCHAT_AUTH_MODE=static is for development/testing only — "
            "do not use in production"
        )
        return StaticTokenVerifier(
            tokens={t: {"client_id": "static", "scopes": []} for t in tokens}
        )

    raise AuthConfigurationError(
        f"Unknown ZULIPCHAT_AUTH_MODE: {mode!r} "
        "(expected none, jwt, google, oidc, or static)"
    )
