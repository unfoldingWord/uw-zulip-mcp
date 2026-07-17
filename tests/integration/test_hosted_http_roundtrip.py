"""End-to-end hosted-mode round-trip over streamable HTTP.

Spins a real FastMCP server (auth + credential middleware) and drives it
with two client identities, proving:
- X-Zulip-* headers coexist with an Authorization-based auth provider
- each request runs as its own identity, with no bleed between users
- unauthenticated and credential-less requests are rejected
"""

import asyncio
import socket
import threading
import time

import pytest
from fastmcp import Client, FastMCP
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.server.auth import StaticTokenVerifier

from src.zulipchat_mcp.core.hosted_middleware import ZulipCredentialMiddleware
from src.zulipchat_mcp.core.request_credentials import (
    get_request_credentials,
    set_hosted_mode,
)

pytestmark = [pytest.mark.integration, pytest.mark.slow]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def hosted_server():
    set_hosted_mode(True)
    port = _free_port()

    verifier = StaticTokenVerifier(
        tokens={"good-token": {"client_id": "test", "scopes": []}}
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


def _client(
    url: str,
    email: str | None = None,
    key: str | None = None,
    token: str | None = "good-token",
):
    headers = {}
    if email:
        headers["X-Zulip-Email"] = email
    if key:
        headers["X-Zulip-Key"] = key
    return Client(StreamableHttpTransport(url, headers=headers, auth=token))


@pytest.mark.asyncio
async def test_two_identities_are_isolated(hosted_server):
    alice = _client(hosted_server, "alice@x.com", "a" * 32)
    bob = _client(hosted_server, "bob@x.com", "b" * 32)
    async with alice, bob:
        results = await asyncio.gather(
            *(alice.call_tool("whoami", {}) for _ in range(3)),
            *(bob.call_tool("whoami", {}) for _ in range(3)),
        )
    emails = [r.data["email"] for r in results]
    assert emails[:3] == ["alice@x.com"] * 3
    assert emails[3:] == ["bob@x.com"] * 3


@pytest.mark.asyncio
async def test_missing_credentials_rejected_in_hosted_mode(hosted_server):
    client = _client(hosted_server)  # OAuth token but no Zulip headers
    async with client:
        with pytest.raises(Exception, match="X-Zulip"):
            await client.call_tool("whoami", {})


@pytest.mark.asyncio
async def test_unauthenticated_client_rejected(hosted_server):
    import httpx

    client = _client(hosted_server, "alice@x.com", "a" * 32, token=None)
    with pytest.raises(httpx.HTTPStatusError):
        async with client:
            await client.call_tool("whoami", {})


@pytest.mark.asyncio
async def test_malformed_key_rejected(hosted_server):
    client = _client(hosted_server, "alice@x.com", "not a real key!")
    async with client:
        with pytest.raises(Exception, match="API key"):
            await client.call_tool("whoami", {})
