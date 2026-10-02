"""Tests for the hosted-mode credential middleware (OAuth2 + vault model)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp.exceptions import ToolError

from src.zulipchat_mcp.core.credential_resolver import (
    CredentialResolutionUnavailable,
    EnrollmentRequired,
    IdentityNotAllowed,
)
from src.zulipchat_mcp.core.hosted_middleware import ZulipCredentialMiddleware
from src.zulipchat_mcp.core.request_credentials import (
    RequestCredentials,
    get_auth_failure_signal,
    get_request_credentials,
    set_hosted_mode,
)

VALID_KEY = "a" * 32
_RESOLVE = "src.zulipchat_mcp.core.hosted_middleware.resolve_request_credentials"
_RUNTIME = "src.zulipchat_mcp.core.hosted_middleware.hosted_runtime"
_FLAG = (
    "src.zulipchat_mcp.core.hosted_middleware.hosted_config.reenroll_on_auth_failure"
)


@pytest.fixture(autouse=True)
def _reset_hosted_mode():
    yield
    set_hosted_mode(False)


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

    creds = RequestCredentials(email="a@b.com", api_key=VALID_KEY)
    with patch(_RESOLVE, new=AsyncMock(return_value=creds)):
        result = await middleware.on_call_tool(context, call_next)

    assert result == "ok"
    assert observed["creds"].email == "a@b.com"
    assert get_request_credentials() is None  # unbound after


@pytest.mark.asyncio
async def test_unbinds_on_exception(middleware, context):
    async def call_next(ctx):
        raise RuntimeError("tool blew up")

    creds = RequestCredentials(email="a@b.com", api_key=VALID_KEY)
    with patch(_RESOLVE, new=AsyncMock(return_value=creds)):
        with pytest.raises(RuntimeError):
            await middleware.on_call_tool(context, call_next)

    assert get_request_credentials() is None


@pytest.mark.asyncio
async def test_local_mode_passthrough(middleware, context):
    """No OAuth identity and not hosted: fall through to env credentials."""
    call_next = AsyncMock(return_value="ok")
    with patch(_RESOLVE, new=AsyncMock(return_value=None)):
        result = await middleware.on_call_tool(context, call_next)
    assert result == "ok"
    call_next.assert_awaited_once()


@pytest.mark.asyncio
async def test_hosted_no_identity_rejected(middleware, context):
    set_hosted_mode(True)
    call_next = AsyncMock()
    with patch(_RESOLVE, new=AsyncMock(return_value=None)):
        with pytest.raises(ToolError, match="no authenticated identity"):
            await middleware.on_call_tool(context, call_next)
    call_next.assert_not_awaited()


@pytest.mark.asyncio
async def test_enrollment_required_returns_link(middleware, context):
    set_hosted_mode(True)
    call_next = AsyncMock()
    err = EnrollmentRequired("new@b.com")
    with patch(_RESOLVE, new=AsyncMock(side_effect=err)):
        with pytest.raises(ToolError, match="/enroll"):
            await middleware.on_call_tool(context, call_next)
    call_next.assert_not_awaited()


@pytest.mark.asyncio
async def test_vault_unavailable_rejected(middleware, context):
    set_hosted_mode(True)
    call_next = AsyncMock()
    err = CredentialResolutionUnavailable("vault down")
    with patch(_RESOLVE, new=AsyncMock(side_effect=err)):
        with pytest.raises(ToolError, match="try again"):
            await middleware.on_call_tool(context, call_next)
    call_next.assert_not_awaited()


@pytest.mark.asyncio
async def test_identity_not_allowed_rejected(middleware, context):
    set_hosted_mode(True)
    call_next = AsyncMock()
    err = IdentityNotAllowed("stranger@gmail.com")
    with patch(_RESOLVE, new=AsyncMock(side_effect=err)):
        with pytest.raises(ToolError, match="not authorized"):
            await middleware.on_call_tool(context, call_next)
    call_next.assert_not_awaited()


@pytest.mark.asyncio
async def test_signal_bound_during_call(middleware, context):
    """A fresh auth-failure signal is visible while the tool runs."""
    observed = {}

    async def call_next(ctx):
        observed["signal"] = get_auth_failure_signal()
        return "ok"

    creds = RequestCredentials(email="a@b.com", api_key=VALID_KEY)
    with patch(_RESOLVE, new=AsyncMock(return_value=creds)):
        await middleware.on_call_tool(context, call_next)

    assert observed["signal"] is not None
    assert get_auth_failure_signal() is None  # unbound after


@pytest.mark.asyncio
async def test_rotated_key_triggers_reenrollment(middleware, context):
    """A tripped signal clears the cache + vault and returns an enrollment link."""
    set_hosted_mode(True)
    cache = MagicMock()
    store = MagicMock()
    store.delete_api_key = AsyncMock()
    runtime = MagicMock()
    runtime.get_key_cache.return_value = cache
    runtime.get_secret_store.return_value = store

    async def call_next(ctx):
        get_auth_failure_signal().trip()  # Zulip rejected the key
        return {"result": "error"}

    creds = RequestCredentials(email="a@b.com", api_key=VALID_KEY)
    with (
        patch(_RESOLVE, new=AsyncMock(return_value=creds)),
        patch(_RUNTIME, runtime),
        patch(_FLAG, return_value=True),
    ):
        with pytest.raises(ToolError, match="/enroll"):
            await middleware.on_call_tool(context, call_next)

    cache.invalidate.assert_called_once_with("a@b.com")
    store.delete_api_key.assert_awaited_once_with("a@b.com")


@pytest.mark.asyncio
async def test_rotated_key_respects_disabled_flag(middleware, context):
    """With the flag off, a tripped signal leaves the key and returns the result."""
    set_hosted_mode(True)
    runtime = MagicMock()

    async def call_next(ctx):
        get_auth_failure_signal().trip()
        return {"result": "error"}

    creds = RequestCredentials(email="a@b.com", api_key=VALID_KEY)
    with (
        patch(_RESOLVE, new=AsyncMock(return_value=creds)),
        patch(_RUNTIME, runtime),
        patch(_FLAG, return_value=False),
    ):
        result = await middleware.on_call_tool(context, call_next)

    assert result == {"result": "error"}
    runtime.get_secret_store.assert_not_called()
