"""Tests for request-scoped credential handling (hosted mode)."""

import pytest

from src.zulipchat_mcp.core.request_credentials import (
    RequestCredentials,
    bind_request_credentials,
    current_cache_scope,
    get_request_credentials,
    is_hosted_mode,
    set_hosted_mode,
    unbind_request_credentials,
)

VALID_KEY = "a" * 32


@pytest.fixture(autouse=True)
def _reset_hosted_mode():
    yield
    set_hosted_mode(False)


class TestRequestCredentials:
    def test_repr_never_leaks_key(self):
        creds = RequestCredentials(email="a@b.com", api_key=VALID_KEY)
        assert VALID_KEY not in repr(creds)
        assert VALID_KEY not in str(creds)
        assert "<redacted>" in repr(creds)

    def test_scope_stable_and_distinct(self):
        a = RequestCredentials(email="a@b.com", api_key=VALID_KEY)
        a2 = RequestCredentials(email="a@b.com", api_key=VALID_KEY)
        b = RequestCredentials(email="b@b.com", api_key="b" * 32)
        assert a.scope == a2.scope
        assert a.scope != b.scope
        assert VALID_KEY not in a.scope

    def test_frozen(self):
        creds = RequestCredentials(email="a@b.com", api_key=VALID_KEY)
        with pytest.raises(AttributeError):
            creds.email = "other@b.com"  # type: ignore[misc]


class TestContextBinding:
    def test_default_is_none(self):
        assert get_request_credentials() is None
        assert current_cache_scope() == ""

    def test_bind_and_unbind(self):
        creds = RequestCredentials(email="a@b.com", api_key=VALID_KEY)
        token = bind_request_credentials(creds)
        try:
            assert get_request_credentials() is creds
            assert current_cache_scope() == creds.scope
        finally:
            unbind_request_credentials(token)
        assert get_request_credentials() is None

    @pytest.mark.asyncio
    async def test_concurrent_tasks_are_isolated(self):
        """Two interleaved asyncio tasks must never see each other's creds."""
        import asyncio

        async def use_identity(email: str, key: str, results: list):
            creds = RequestCredentials(email=email, api_key=key)
            token = bind_request_credentials(creds)
            try:
                await asyncio.sleep(0.01)  # force interleaving
                bound = get_request_credentials()
                results.append((email, bound.email if bound else None))
                await asyncio.sleep(0.01)
                bound2 = get_request_credentials()
                results.append((email, bound2.email if bound2 else None))
            finally:
                unbind_request_credentials(token)

        results: list = []
        await asyncio.gather(
            use_identity("alice@x.com", "a" * 32, results),
            use_identity("bob@x.com", "b" * 32, results),
        )
        for expected, observed in results:
            assert expected == observed


class TestHostedMode:
    def test_default_off(self):
        assert is_hosted_mode() is False

    def test_toggle(self):
        set_hosted_mode(True)
        assert is_hosted_mode() is True
        set_hosted_mode(False)
        assert is_hosted_mode() is False
