"""Tests for the env-driven OAuth auth provider factory."""

import pytest

from src.zulipchat_mcp.core.auth_provider import (
    AuthConfigurationError,
    build_auth_provider,
)


@pytest.fixture(autouse=True)
def _clean_auth_env(monkeypatch):
    for var in (
        "ZULIPCHAT_AUTH_MODE",
        "ZULIPCHAT_AUTH_JWKS_URI",
        "ZULIPCHAT_AUTH_ISSUER",
        "ZULIPCHAT_AUTH_AUDIENCE",
        "ZULIPCHAT_AUTH_CLIENT_ID",
        "ZULIPCHAT_AUTH_CLIENT_SECRET",
        "ZULIPCHAT_AUTH_BASE_URL",
        "ZULIPCHAT_AUTH_CONFIG_URL",
        "ZULIPCHAT_AUTH_STATIC_TOKENS",
    ):
        monkeypatch.delenv(var, raising=False)


def test_default_is_no_auth():
    assert build_auth_provider() is None


def test_explicit_none():
    import os

    os.environ["ZULIPCHAT_AUTH_MODE"] = "none"
    try:
        assert build_auth_provider() is None
    finally:
        del os.environ["ZULIPCHAT_AUTH_MODE"]


def test_unknown_mode_rejected(monkeypatch):
    monkeypatch.setenv("ZULIPCHAT_AUTH_MODE", "carrier-pigeon")
    with pytest.raises(AuthConfigurationError, match="Unknown"):
        build_auth_provider()


def test_jwt_requires_config(monkeypatch):
    monkeypatch.setenv("ZULIPCHAT_AUTH_MODE", "jwt")
    with pytest.raises(AuthConfigurationError, match="ZULIPCHAT_AUTH_JWKS_URI"):
        build_auth_provider()


def test_jwt_builds_verifier(monkeypatch):
    monkeypatch.setenv("ZULIPCHAT_AUTH_MODE", "jwt")
    monkeypatch.setenv(
        "ZULIPCHAT_AUTH_JWKS_URI", "https://idp.example.com/.well-known/jwks.json"
    )
    monkeypatch.setenv("ZULIPCHAT_AUTH_ISSUER", "https://idp.example.com")
    provider = build_auth_provider()
    from fastmcp.server.auth import JWTVerifier

    assert isinstance(provider, JWTVerifier)


def test_google_requires_config(monkeypatch):
    monkeypatch.setenv("ZULIPCHAT_AUTH_MODE", "google")
    with pytest.raises(AuthConfigurationError, match="ZULIPCHAT_AUTH_CLIENT_ID"):
        build_auth_provider()


def test_static_builds_verifier(monkeypatch):
    monkeypatch.setenv("ZULIPCHAT_AUTH_MODE", "static")
    monkeypatch.setenv("ZULIPCHAT_AUTH_STATIC_TOKENS", "tok-a, tok-b")
    provider = build_auth_provider()
    from fastmcp.server.auth import StaticTokenVerifier

    assert isinstance(provider, StaticTokenVerifier)


def test_static_requires_tokens(monkeypatch):
    monkeypatch.setenv("ZULIPCHAT_AUTH_MODE", "static")
    monkeypatch.setenv("ZULIPCHAT_AUTH_STATIC_TOKENS", " , ")
    with pytest.raises(AuthConfigurationError):
        build_auth_provider()
