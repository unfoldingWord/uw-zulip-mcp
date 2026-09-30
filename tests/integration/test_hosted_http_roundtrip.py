"""End-to-end hosted-mode round-trip over streamable HTTP (OAuth2 + vault).

Spins a real FastMCP server (OAuth auth + credential middleware) and drives it
with two OAuth identities, proving:
- the user's Zulip identity is derived from the OAuth token and resolved from
  the vault/cache, with no bleed between concurrent users
- an authenticated user with no stored key is told to enrol
- an unauthenticated request is rejected
"""

import asyncio
import socket
import threading
import time

import pytest
from fastmcp import Client, FastMCP
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.server.auth import StaticTokenVerifier

from src.zulipchat_mcp.core import hosted_runtime
from src.zulipchat_mcp.core.hosted_middleware import ZulipCredentialMiddleware
from src.zulipchat_mcp.core.key_cache import SlidingKeyCache
from src.zulipchat_mcp.core.request_credentials import (
    get_request_credentials,
    set_hosted_mode,
)

pytestmark = [pytest.mark.integration, pytest.mark.slow]


class _FakeStore:
    """In-memory stand-in for the OpenBao SecretStore."""

    def __init__(self, keys):
        self.keys = dict(keys)

    async def get_api_key(self, email):
        return self.keys.get(email.lower())

    async def set_api_key(self, email, api_key):
        self.keys[email.lower()] = api_key

    async def aclose(self):
        pass


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def hosted_server():
    set_hosted_mode(True)
    hosted_runtime.set_secret_store(
        _FakeStore({"alice@x.com": "a" * 32, "bob@x.com": "b" * 32})
    )
    hosted_runtime.set_key_cache(SlidingKeyCache(ttl_seconds=3600))
    port = _free_port()

    verifier = StaticTokenVerifier(
        tokens={
            "tok-alice": {"client_id": "t", "scopes": [], "email": "alice@x.com"},
            "tok-bob": {"client_id": "t", "scopes": [], "email": "bob@x.com"},
            "tok-new": {"client_id": "t", "scopes": [], "email": "new@x.com"},
        }
    )
    mcp = FastMCP("hosted-test", auth=verifier)
    mcp.add_middleware(ZulipCredentialMiddleware())

    @mcp.tool
    def whoami() -> dict:
        creds = get_request_credentials()
        return {"email": creds.email if creds else None}

    thread = threading.Thread(
        target=lambda: mcp.run(
            transport="http", host="127.0.0.1", port=port, show_banner=False
        ),
        daemon=True,
    )
    thread.start()
    time.sleep(1.5)
    yield f"http://127.0.0.1:{port}/mcp"
    set_hosted_mode(False)
    hosted_runtime.reset()


def _client(url: str, token: str | None = "tok-alice"):
    return Client(StreamableHttpTransport(url, auth=token))


@pytest.mark.asyncio
async def test_two_identities_are_isolated(hosted_server):
    alice = _client(hosted_server, "tok-alice")
    bob = _client(hosted_server, "tok-bob")
    async with alice, bob:
        results = await asyncio.gather(
            *(alice.call_tool("whoami", {}) for _ in range(3)),
            *(bob.call_tool("whoami", {}) for _ in range(3)),
        )
    emails = [r.data["email"] for r in results]
    assert emails[:3] == ["alice@x.com"] * 3
    assert emails[3:] == ["bob@x.com"] * 3


@pytest.mark.asyncio
async def test_user_without_key_is_told_to_enrol(hosted_server):
    client = _client(hosted_server, "tok-new")  # authenticated, but no stored key
    async with client:
        with pytest.raises(Exception, match="enroll"):
            await client.call_tool("whoami", {})


@pytest.mark.asyncio
async def test_unauthenticated_client_rejected(hosted_server):
    client = _client(hosted_server, token=None)
    with pytest.raises(Exception):  # noqa: B017
        async with client:
            await client.call_tool("whoami", {})
