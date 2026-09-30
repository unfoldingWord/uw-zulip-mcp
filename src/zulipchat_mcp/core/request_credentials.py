"""Request-scoped Zulip credentials for hosted (multi-user) deployments.

In OAuth2-only hosted mode the user's Zulip API key is resolved from the vault
(see credential_resolver.py) based on their OAuth identity, then bound here for
the duration of the request. Credentials live only in a contextvar for the
duration of the request — never written to disk, database, or logs. The Zulip
site is always pinned server-side (ZULIP_SITE); clients cannot redirect the
server to another host.

This module holds the reusable plumbing: the RequestCredentials value object,
the contextvar binding, the hosted-mode flag, and the per-identity cache scope.
"""

from __future__ import annotations

import hashlib
from contextvars import ContextVar, Token
from dataclasses import dataclass, field


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
