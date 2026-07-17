"""Request-scoped Zulip credentials for hosted (multi-user) deployments.

In hosted mode the MCP client supplies the user's Zulip credentials with
every HTTP request via headers. Credentials live only in a contextvar for
the duration of the request — they are never written to disk, database,
or logs. The Zulip site is always pinned server-side (ZULIP_SITE); clients
cannot redirect the server to another host.

Header contract (case-insensitive on the wire):
    X-Zulip-Email: user@example.com
    X-Zulip-Key:   <32-char Zulip API key>
"""

from __future__ import annotations

import hashlib
import re
from contextvars import ContextVar, Token
from dataclasses import dataclass, field

HEADER_EMAIL = "x-zulip-email"
HEADER_KEY = "x-zulip-key"

# Zulip API keys are 32 alphanumeric chars; allow margin for future changes.
_API_KEY_RE = re.compile(r"^[A-Za-z0-9]{20,64}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class CredentialResolutionError(ValueError):
    """Raised when credential headers are present but malformed/incomplete.

    The message is safe to surface to the MCP client — it never contains
    credential material.
    """


@dataclass(frozen=True, repr=False)
class RequestCredentials:
    """Per-request Zulip user credentials. Never persisted."""

    email: str
    api_key: str = field()

    def __repr__(self) -> str:  # never leak the key via repr/str/tracebacks
        return f"RequestCredentials(email={self.email!r}, api_key=<redacted>)"

    __str__ = __repr__

    @property
    def scope(self) -> str:
        """Stable, non-reversible cache-scope token for this identity."""
        digest = hashlib.sha256(f"{self.email}:{self.api_key}".encode()).hexdigest()
        return digest[:16]


_request_credentials: ContextVar[RequestCredentials | None] = ContextVar(
    "zulip_request_credentials", default=None
)

# Process-level hosted-mode flag, set once at server startup.
_hosted_mode: bool = False


def set_hosted_mode(enabled: bool) -> None:
    """Enable/disable hosted mode. Called once from server startup."""
    global _hosted_mode
    _hosted_mode = enabled


def is_hosted_mode() -> bool:
    """True when the server runs as a hosted multi-user deployment."""
    return _hosted_mode


def get_request_credentials() -> RequestCredentials | None:
    """Credentials bound to the current request, if any."""
    return _request_credentials.get()


def bind_request_credentials(
    creds: RequestCredentials | None,
) -> Token[RequestCredentials | None]:
    """Bind credentials to the current context. Pair with unbind in finally."""
    return _request_credentials.set(creds)


def unbind_request_credentials(token: Token[RequestCredentials | None]) -> None:
    """Restore the previous credential binding."""
    _request_credentials.reset(token)


def current_cache_scope() -> str:
    """Cache-key scope for the current identity.

    Empty string in single-user (stdio) mode so existing cache behavior
    is unchanged; a per-identity token in hosted mode so cached data can
    never be served across users.
    """
    creds = get_request_credentials()
    return creds.scope if creds is not None else ""


def resolve_credentials_from_headers() -> RequestCredentials | None:
    """Extract and validate Zulip credentials from the current HTTP request.

    Returns None when no credential headers are present (stdio transport,
    or an HTTP client that has not supplied them). Raises
    CredentialResolutionError when headers are present but invalid.
    """
    from fastmcp.server.dependencies import get_http_headers

    headers = get_http_headers()  # {} outside an HTTP request
    email = (headers.get(HEADER_EMAIL) or "").strip()
    api_key = (headers.get(HEADER_KEY) or "").strip()

    if not email and not api_key:
        return None
    if not email or not api_key:
        raise CredentialResolutionError(
            "Both X-Zulip-Email and X-Zulip-Key headers are required."
        )
    if not _EMAIL_RE.match(email):
        raise CredentialResolutionError("X-Zulip-Email is not a valid email address.")
    if not _API_KEY_RE.match(api_key):
        raise CredentialResolutionError(
            "X-Zulip-Key does not look like a Zulip API key."
        )
    return RequestCredentials(email=email, api_key=api_key)
