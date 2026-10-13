"""Two-tier request settings: server-only **policy** vs client-overridable **preferences**.

The server has always sourced settings from env/CLI only; nothing was
client-overridable. This module introduces, explicitly and in one place, the
small set of settings a *client* may override per request via an HTTP header.

Two tiers:

- **Policy** (server-only, never client-touchable): read-only, disable-agents,
  the channel filter, the identity allowlist, unsafe mode, and the
  single-message link default below. These come from env/CLI, full stop — no
  header can change them.
- **Preferences** (server default + optional per-request client override): the
  entries in ``REQUEST_OVERRIDABLE`` below, and only those. A key here can be
  flipped by its HTTP header; a key *not* here can never be.

Security boundary: client headers are untrusted input. Only registry keys are
ever read from a header. **Never add a security/policy setting to the registry**
— `tests/core/test_request_prefs.py` enforces that policy keys stay out.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastmcp.server.dependencies import get_http_headers

from ..utils.env import env_bool, parse_bool


@dataclass(frozen=True)
class OverridablePref:
    """A client-overridable preference: server default plus a header override."""

    key: str
    env_var: str
    default: bool
    header: str  # canonical display spelling; lookups are case-insensitive

    @property
    def header_key(self) -> str:
        return self.header.lower()


# The ONLY client-overridable preferences. Keep this list small and cosmetic;
# nothing with security or access-control weight belongs here.
REQUEST_OVERRIDABLE: dict[str, OverridablePref] = {
    "links_search": OverridablePref(
        key="links_search",
        env_var="ZULIPCHAT_MESSAGE_LINKS_SEARCH",
        default=False,
        header="X-Zulipchat-MCP-Links-Search",
    ),
}


def pref_enabled(key: str) -> bool:
    """Effective value of an overridable preference for the current request.

    Resolution: the server default (``env_var``) unless the request carries the
    preference's header, in which case the header wins. With no active HTTP
    request (stdio), ``get_http_headers()`` returns ``{}`` and the server default
    applies.
    """
    pref = REQUEST_OVERRIDABLE[key]
    value = env_bool(pref.env_var, pref.default)
    raw = get_http_headers().get(pref.header_key)
    if raw is not None:
        value = parse_bool(raw, value)
    return value


# --- Policy settings (server-only; NOT in the registry, never header-overridable) ---


def message_link_single_enabled() -> bool:
    """Whether single-message tools (e.g. get_message) include a permalink.

    Policy, not a preference: sourced from env only, with no header override.
    Default on.
    """
    return env_bool("ZULIPCHAT_MESSAGE_LINK_SINGLE", True)
