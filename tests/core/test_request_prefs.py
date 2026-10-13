"""Tests for the two-tier request settings (policy vs. overridable preference).

The critical test is the trust boundary: a client header must never affect a
policy setting, and only registry keys may be overridden.
"""

from __future__ import annotations

from src.zulipchat_mcp.core import request_prefs
from src.zulipchat_mcp.core.request_prefs import (
    REQUEST_OVERRIDABLE,
    message_link_single_enabled,
    pref_enabled,
)

_HEADER = "x-zulipchat-mcp-links-search"


def _fake_headers(mapping):
    """Patch get_http_headers (used inside request_prefs) to return `mapping`."""

    def _patch(monkeypatch):
        monkeypatch.setattr(
            request_prefs, "get_http_headers", lambda *a, **k: dict(mapping)
        )

    return _patch


# --- the overridable preference: server default + header override ----------


def test_links_search_defaults_off(monkeypatch):
    monkeypatch.delenv("ZULIPCHAT_MESSAGE_LINKS_SEARCH", raising=False)
    monkeypatch.setattr(request_prefs, "get_http_headers", lambda *a, **k: {})
    assert pref_enabled("links_search") is False


def test_links_search_env_default_on(monkeypatch):
    monkeypatch.setenv("ZULIPCHAT_MESSAGE_LINKS_SEARCH", "true")
    monkeypatch.setattr(request_prefs, "get_http_headers", lambda *a, **k: {})
    assert pref_enabled("links_search") is True


def test_header_overrides_env_on(monkeypatch):
    monkeypatch.delenv("ZULIPCHAT_MESSAGE_LINKS_SEARCH", raising=False)  # default off
    monkeypatch.setattr(
        request_prefs, "get_http_headers", lambda *a, **k: {_HEADER: "on"}
    )
    assert pref_enabled("links_search") is True


def test_header_overrides_env_off(monkeypatch):
    monkeypatch.setenv("ZULIPCHAT_MESSAGE_LINKS_SEARCH", "true")  # default on
    monkeypatch.setattr(
        request_prefs, "get_http_headers", lambda *a, **k: {_HEADER: "off"}
    )
    assert pref_enabled("links_search") is False


def test_malformed_header_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("ZULIPCHAT_MESSAGE_LINKS_SEARCH", "true")
    monkeypatch.setattr(
        request_prefs, "get_http_headers", lambda *a, **k: {_HEADER: "banana"}
    )
    assert pref_enabled("links_search") is True


# --- the trust boundary: policy settings are never header-overridable ------


def test_single_link_is_policy_not_header_overridable(monkeypatch):
    # Even with a bogus header present, the single-message link reads ONLY its
    # env var — a client cannot flip it.
    monkeypatch.delenv("ZULIPCHAT_MESSAGE_LINK_SINGLE", raising=False)  # default on
    monkeypatch.setattr(
        request_prefs,
        "get_http_headers",
        lambda *a, **k: {"x-zulipchat-mcp-link-single": "off"},
    )
    assert message_link_single_enabled() is True  # header ignored

    monkeypatch.setenv("ZULIPCHAT_MESSAGE_LINK_SINGLE", "false")
    assert message_link_single_enabled() is False  # only env changes it


def test_registry_contains_no_policy_keys():
    # The guardrail: security/policy settings must never be client-overridable.
    policy_keys = {
        "read_only",
        "disable_agents",
        "unsafe",
        "channel_filter",
        "identity_allowlist",
        "allowed_email_domains",
        "allowed_emails",
        "links_single",
    }
    assert policy_keys.isdisjoint(REQUEST_OVERRIDABLE.keys())
    # And the only overridable key today is the cosmetic search-links toggle.
    assert set(REQUEST_OVERRIDABLE.keys()) == {"links_search"}
