"""Tests for the hosted-mode credential middleware."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp.exceptions import ToolError

from src.zulipchat_mcp.core.hosted_middleware import ZulipCredentialMiddleware
from src.zulipchat_mcp.core.request_credentials import (
    get_request_credentials,
    set_hosted_mode,
)

VALID_KEY = "a" * 32


@pytest.fixture(autouse=True)
def _reset_hosted_mode():
    yield
    set_hosted_mode(False)


def _headers(headers: dict):
    return patch(
        "fastmcp.server.dependencies.get_http_headers",
        return_value=headers,
    )


@pytest.fixture
def middleware():
    return ZulipCredentialMiddleware()


@pytest.fixture
def context():
    return MagicMock()


@pytest.mark.asyncio
async def test_binds_credentials_during_call(middleware, context):
    observed = {}

    async def call_next(ctx):
        observed["creds"] = get_request_credentials()
        return "ok"

    with _headers({"x-zulip-email": "a@b.com", "x-zulip-key": VALID_KEY}):
        result = await middleware.on_call_tool(context, call_next)

    assert result == "ok"
    assert observed["creds"] is not None
    assert observed["creds"].email == "a@b.com"
    # Unbound after the call
    assert get_request_credentials() is None


@pytest.mark.asyncio
async def test_unbinds_on_exception(middleware, context):
    async def call_next(ctx):
        raise RuntimeError("tool blew up")

    with _headers({"x-zulip-email": "a@b.com", "x-zulip-key": VALID_KEY}):
        with pytest.raises(RuntimeError):
            await middleware.on_call_tool(context, call_next)

    assert get_request_credentials() is None


@pytest.mark.asyncio
async def test_no_headers_passthrough_in_local_mode(middleware, context):
    call_next = AsyncMock(return_value="ok")
    with _headers({}):
        result = await middleware.on_call_tool(context, call_next)
    assert result == "ok"
    call_next.assert_awaited_once()


@pytest.mark.asyncio
async def test_hosted_mode_requires_credentials(middleware, context):
    set_hosted_mode(True)
    call_next = AsyncMock()
    with _headers({}):
        with pytest.raises(ToolError, match="X-Zulip-Email"):
            await middleware.on_call_tool(context, call_next)
    call_next.assert_not_awaited()


@pytest.mark.asyncio
async def test_malformed_credentials_rejected(middleware, context):
    call_next = AsyncMock()
    with _headers({"x-zulip-email": "a@b.com", "x-zulip-key": "bad key!"}):
        with pytest.raises(ToolError):
            await middleware.on_call_tool(context, call_next)
    call_next.assert_not_awaited()


@pytest.mark.asyncio
async def test_email_match_enforced_when_enabled(middleware, context, monkeypatch):
    monkeypatch.setenv("ZULIPCHAT_REQUIRE_EMAIL_MATCH", "1")
    call_next = AsyncMock()

    token = MagicMock()
    token.claims = {"email": "someone-else@b.com"}
    with _headers({"x-zulip-email": "a@b.com", "x-zulip-key": VALID_KEY}):
        with patch("fastmcp.server.dependencies.get_access_token", return_value=token):
            with pytest.raises(ToolError, match="does not match"):
                await middleware.on_call_tool(context, call_next)
    call_next.assert_not_awaited()


@pytest.mark.asyncio
async def test_email_match_passes_on_same_identity(middleware, context, monkeypatch):
    monkeypatch.setenv("ZULIPCHAT_REQUIRE_EMAIL_MATCH", "1")
    call_next = AsyncMock(return_value="ok")

    token = MagicMock()
    token.claims = {"email": "A@B.com"}  # case-insensitive match
    with _headers({"x-zulip-email": "a@b.com", "x-zulip-key": VALID_KEY}):
        with patch("fastmcp.server.dependencies.get_access_token", return_value=token):
            result = await middleware.on_call_tool(context, call_next)
    assert result == "ok"


@pytest.mark.asyncio
async def test_email_match_skipped_without_oauth_token(
    middleware, context, monkeypatch
):
    """No auth provider (e.g. proxy-fronted deployment) — match check is moot."""
    monkeypatch.setenv("ZULIPCHAT_REQUIRE_EMAIL_MATCH", "1")
    call_next = AsyncMock(return_value="ok")
    with _headers({"x-zulip-email": "a@b.com", "x-zulip-key": VALID_KEY}):
        with patch("fastmcp.server.dependencies.get_access_token", return_value=None):
            result = await middleware.on_call_tool(context, call_next)
    assert result == "ok"
