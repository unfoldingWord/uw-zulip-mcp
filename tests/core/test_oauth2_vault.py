"""Tests for the OAuth2-only, vault-backed credential flow."""

from __future__ import annotations

import httpx
import pytest

from src.zulipchat_mcp.core import credential_resolver, enrollment, hosted_runtime
from src.zulipchat_mcp.core.enrollment import (
    CoolOff,
    EnrollOutcome,
    EnrollResult,
    UsedTokens,
    enrollment_token_expiry,
    mint_enrollment_token,
    try_enroll,
    verify_enrollment_token,
)
from src.zulipchat_mcp.core.key_cache import SlidingKeyCache
from src.zulipchat_mcp.core.secret_store import SecretStore, SecretStoreError

SECRET = "unit-test-secret"
KEY = "a" * 32


@pytest.fixture(autouse=True)
def _reset_runtime():
    hosted_runtime.reset()
    yield
    hosted_runtime.reset()


# --- key cache -------------------------------------------------------------


def test_cache_hit_and_miss():
    cache = SlidingKeyCache(ttl_seconds=100)
    assert cache.get("u@x.org") is None
    cache.set("U@x.org", KEY)
    # case-insensitive
    assert cache.get("u@x.org") == KEY


def test_cache_sliding_expiry(monkeypatch):
    cache = SlidingKeyCache(ttl_seconds=10)
    t = [1000.0]
    monkeypatch.setattr("src.zulipchat_mcp.core.key_cache.time.monotonic", lambda: t[0])
    cache.set("u@x.org", KEY)
    t[0] = 1005.0  # within TTL, refreshes timer
    assert cache.get("u@x.org") == KEY
    t[0] = 1014.0  # 9s after last access, still alive
    assert cache.get("u@x.org") == KEY
    t[0] = 1030.0  # >10s inactivity
    assert cache.get("u@x.org") is None


def test_cache_invalidate():
    cache = SlidingKeyCache(ttl_seconds=100)
    cache.set("u@x.org", KEY)
    cache.invalidate("u@x.org")
    assert cache.get("u@x.org") is None


# --- enrollment token ------------------------------------------------------


def test_token_roundtrip():
    tok = mint_enrollment_token("User@x.org", secret=SECRET, ttl_seconds=60)
    assert verify_enrollment_token(tok, secret=SECRET) == "user@x.org"


def test_token_rejects_tamper():
    tok = mint_enrollment_token("u@x.org", secret=SECRET, ttl_seconds=60)
    assert verify_enrollment_token(tok, secret="other-secret") is None
    assert verify_enrollment_token(tok + "x", secret=SECRET) is None
    assert verify_enrollment_token("garbage", secret=SECRET) is None


def test_token_expiry():
    tok = mint_enrollment_token("u@x.org", secret=SECRET, ttl_seconds=-1)
    assert verify_enrollment_token(tok, secret=SECRET) is None


# --- cool-off --------------------------------------------------------------


def test_cooloff_locks_after_max():
    co = CoolOff(max_attempts=3, cooloff_seconds=100)
    assert co.record_failure("u@x.org") == 2
    assert co.record_failure("u@x.org") == 1
    assert co.record_failure("u@x.org") == 0  # locked now
    assert co.seconds_remaining("u@x.org") > 0


def test_cooloff_reset():
    co = CoolOff(max_attempts=3, cooloff_seconds=100)
    co.record_failure("u@x.org")
    co.reset("u@x.org")
    assert co.record_failure("u@x.org") == 2  # counter restarted


# --- Zulip key validation (mocked HTTP) ------------------------------------


def _patch_httpx(monkeypatch, module, handler):
    real_client = httpx.AsyncClient  # capture before patching

    def factory(**kwargs):
        kwargs.pop("verify", None)
        kwargs.pop("transport", None)
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(module.httpx, "AsyncClient", factory)


async def test_validate_key_ok(monkeypatch):
    def handler(request):
        assert request.url.path == "/api/v1/users/me"
        assert request.headers.get("authorization", "").startswith("Basic ")
        return httpx.Response(200, json={"delivery_email": "u@x.org"})

    _patch_httpx(monkeypatch, enrollment, handler)
    email = await enrollment.validate_zulip_key("https://z.example", "u@x.org", KEY)
    assert email == "u@x.org"


async def test_validate_key_rejected(monkeypatch):
    _patch_httpx(monkeypatch, enrollment, lambda r: httpx.Response(401, json={}))
    assert (
        await enrollment.validate_zulip_key("https://z.example", "u@x.org", KEY) is None
    )


async def test_validate_key_upstream_error(monkeypatch):
    def boom(request):
        raise httpx.ConnectError("down")

    _patch_httpx(monkeypatch, enrollment, boom)
    with pytest.raises(enrollment.ZulipValidationError):
        await enrollment.validate_zulip_key("https://z.example", "u@x.org", KEY)


# --- SecretStore (mocked OpenBao) ------------------------------------------


def _bao_store(handler) -> SecretStore:
    store = SecretStore(
        addr="https://bao.example", token="root-token", kv_mount="secret"
    )
    store._client = httpx.AsyncClient(
        base_url="https://bao.example", transport=httpx.MockTransport(handler)
    )
    return store


async def test_secretstore_get_set_roundtrip():
    saved: dict[str, dict] = {}

    def handler(request):
        path = request.url.path
        if request.method == "POST" and path.startswith("/v1/secret/data/"):
            import json

            saved[path] = json.loads(request.content)["data"]
            return httpx.Response(200, json={"data": {"version": 1}})
        if request.method == "GET" and path.startswith("/v1/secret/data/"):
            if path in saved:
                return httpx.Response(200, json={"data": {"data": saved[path]}})
            return httpx.Response(404, json={"errors": []})
        return httpx.Response(500, json={})

    store = _bao_store(handler)
    assert await store.get_api_key("u@x.org") is None  # not stored yet
    await store.set_api_key("u@x.org", KEY)
    assert await store.get_api_key("u@x.org") == KEY


async def test_secretstore_read_error_raises():
    store = _bao_store(lambda r: httpx.Response(500, text="boom"))
    with pytest.raises(SecretStoreError):
        await store.get_api_key("u@x.org")


def test_secretstore_hashed_path_is_deterministic_and_clean():
    store = SecretStore(addr="https://bao.example", token="t")
    p1 = store.user_path("User@x.org")
    p2 = store.user_path("user@x.org")
    assert p1 == p2  # case-insensitive, same hash
    assert "@" not in p1 and p1.startswith("zulip-mcp/users/")


# --- credential resolver ---------------------------------------------------


class _FakeStore:
    def __init__(self, keys=None, fail=False):
        self.keys = keys or {}
        self.fail = fail
        self.get_calls = 0

    async def get_api_key(self, email):
        self.get_calls += 1
        if self.fail:
            raise SecretStoreError("vault down")
        return self.keys.get(email.lower())


async def test_resolver_cache_hit_skips_vault(monkeypatch):
    monkeypatch.setattr(credential_resolver, "oauth_email", lambda: "u@x.org")
    cache = SlidingKeyCache(ttl_seconds=100)
    cache.set("u@x.org", KEY)
    store = _FakeStore()
    hosted_runtime.set_key_cache(cache)
    hosted_runtime.set_secret_store(store)

    creds = await credential_resolver.resolve_request_credentials()
    assert creds is not None and creds.email == "u@x.org" and creds.api_key == KEY
    assert store.get_calls == 0  # never hit the vault


async def test_resolver_vault_hit_fills_cache(monkeypatch):
    monkeypatch.setattr(credential_resolver, "oauth_email", lambda: "u@x.org")
    cache = SlidingKeyCache(ttl_seconds=100)
    store = _FakeStore(keys={"u@x.org": KEY})
    hosted_runtime.set_key_cache(cache)
    hosted_runtime.set_secret_store(store)

    creds = await credential_resolver.resolve_request_credentials()
    assert creds is not None and creds.api_key == KEY
    assert cache.get("u@x.org") == KEY  # cached for next time


async def test_resolver_no_key_requires_enrollment(monkeypatch):
    monkeypatch.setattr(credential_resolver, "oauth_email", lambda: "new@x.org")
    hosted_runtime.set_key_cache(SlidingKeyCache(ttl_seconds=100))
    hosted_runtime.set_secret_store(_FakeStore())

    with pytest.raises(credential_resolver.EnrollmentRequired) as ei:
        await credential_resolver.resolve_request_credentials()
    assert ei.value.email == "new@x.org"


async def test_resolver_vault_down(monkeypatch):
    monkeypatch.setattr(credential_resolver, "oauth_email", lambda: "u@x.org")
    hosted_runtime.set_key_cache(SlidingKeyCache(ttl_seconds=100))
    hosted_runtime.set_secret_store(_FakeStore(fail=True))

    with pytest.raises(credential_resolver.CredentialResolutionUnavailable):
        await credential_resolver.resolve_request_credentials()


async def test_resolver_no_identity_returns_none(monkeypatch):
    monkeypatch.setattr(credential_resolver, "oauth_email", lambda: None)
    creds = await credential_resolver.resolve_request_credentials()
    assert creds is None


async def test_resolver_isolates_two_users(monkeypatch):
    cache = SlidingKeyCache(ttl_seconds=100)
    store = _FakeStore(keys={"a@x.org": "a" * 32, "b@x.org": "b" * 32})
    hosted_runtime.set_key_cache(cache)
    hosted_runtime.set_secret_store(store)

    monkeypatch.setattr(credential_resolver, "oauth_email", lambda: "a@x.org")
    creds_a = await credential_resolver.resolve_request_credentials()
    monkeypatch.setattr(credential_resolver, "oauth_email", lambda: "b@x.org")
    creds_b = await credential_resolver.resolve_request_credentials()

    assert creds_a.api_key == "a" * 32
    assert creds_b.api_key == "b" * 32


# --- try_enroll end to end -------------------------------------------------


async def test_enroll_success_stores_and_caches(monkeypatch):
    monkeypatch.setattr(enrollment, "validate_zulip_key", _fake_validate("u@x.org"))
    cache = SlidingKeyCache(ttl_seconds=100)
    store = _FakeStore()
    store.set_api_key = _record_set(store)  # type: ignore[method-assign]
    co = CoolOff(max_attempts=6, cooloff_seconds=100)

    res = await try_enroll(
        email="u@x.org",
        api_key=KEY,
        site="https://z",
        store=store,
        cache=cache,
        cooloff=co,
    )
    assert res.outcome is EnrollOutcome.SUCCESS
    assert store.saved == ("u@x.org", KEY)
    assert cache.get("u@x.org") == KEY


async def test_enroll_invalid_key_not_stored(monkeypatch):
    monkeypatch.setattr(enrollment, "validate_zulip_key", _fake_validate(None))
    cache = SlidingKeyCache(ttl_seconds=100)
    store = _FakeStore()
    store.set_api_key = _record_set(store)  # type: ignore[method-assign]
    co = CoolOff(max_attempts=6, cooloff_seconds=100)

    res = await try_enroll(
        email="u@x.org",
        api_key="bad",
        site="https://z",
        store=store,
        cache=cache,
        cooloff=co,
    )
    assert res.outcome is EnrollOutcome.INVALID_KEY
    assert res.remaining_tries == 5
    assert store.saved is None
    assert cache.get("u@x.org") is None


async def test_enroll_email_mismatch_rejected(monkeypatch):
    monkeypatch.setattr(
        enrollment, "validate_zulip_key", _fake_validate("someone-else@x.org")
    )
    store = _FakeStore()
    store.set_api_key = _record_set(store)  # type: ignore[method-assign]
    res = await try_enroll(
        email="u@x.org",
        api_key=KEY,
        site="https://z",
        store=store,
        cache=SlidingKeyCache(ttl_seconds=100),
        cooloff=CoolOff(max_attempts=6, cooloff_seconds=100),
    )
    assert res.outcome is EnrollOutcome.EMAIL_MISMATCH
    assert store.saved is None


async def test_enroll_locks_after_max_failures(monkeypatch):
    monkeypatch.setattr(enrollment, "validate_zulip_key", _fake_validate(None))
    co = CoolOff(max_attempts=3, cooloff_seconds=100)
    store = _FakeStore()
    store.set_api_key = _record_set(store)  # type: ignore[method-assign]
    kw = {
        "email": "u@x.org",
        "api_key": "bad",
        "site": "https://z",
        "store": store,
        "cache": SlidingKeyCache(ttl_seconds=100),
        "cooloff": co,
    }
    await try_enroll(**kw)
    await try_enroll(**kw)
    r3 = await try_enroll(**kw)  # third failure locks
    r4 = await try_enroll(**kw)  # now in cool-off
    assert r3.outcome is EnrollOutcome.INVALID_KEY
    assert r4.outcome is EnrollOutcome.LOCKED
    assert r4.cooloff_seconds and r4.cooloff_seconds > 0


def _fake_validate(return_email):
    async def _v(site, email, api_key):
        return return_email

    return _v


def _record_set(store):
    async def _set(email, api_key):
        store.saved = (email, api_key)

    store.saved = None
    return _set


# --- enrollment web routes -------------------------------------------------


def _enroll_app():
    from starlette.applications import Starlette
    from starlette.routing import Route

    from src.zulipchat_mcp.core import enrollment_routes

    return Starlette(
        routes=[
            Route("/enroll", enrollment_routes.enroll_get, methods=["GET"]),
            Route("/enroll", enrollment_routes.enroll_post, methods=["POST"]),
        ]
    )


def test_enroll_get_invalid_token(monkeypatch):
    from starlette.testclient import TestClient

    monkeypatch.setenv("ZULIPCHAT_ENROLL_SECRET", SECRET)
    resp = TestClient(_enroll_app()).get("/enroll?token=bad")
    assert resp.status_code == 400
    assert "invalid" in resp.text.lower()


def test_enroll_get_valid_token_shows_form(monkeypatch):
    from starlette.testclient import TestClient

    monkeypatch.setenv("ZULIPCHAT_ENROLL_SECRET", SECRET)
    tok = mint_enrollment_token("u@x.org")
    resp = TestClient(_enroll_app()).get(f"/enroll?token={tok}")
    assert resp.status_code == 200
    assert "u@x.org" in resp.text
    assert "API key" in resp.text
    # security headers present
    assert resp.headers.get("Cache-Control") == "no-store"


def test_enroll_post_success(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    from starlette.testclient import TestClient

    from src.zulipchat_mcp.core import enrollment_routes

    monkeypatch.setenv("ZULIPCHAT_ENROLL_SECRET", SECRET)
    tok = mint_enrollment_token("u@x.org")
    cfg = MagicMock()
    cfg.config.site = "https://z.example"
    monkeypatch.setattr(enrollment_routes, "get_config_manager", lambda: cfg)
    monkeypatch.setattr(
        enrollment_routes,
        "try_enroll",
        AsyncMock(return_value=EnrollResult(EnrollOutcome.SUCCESS, "ok")),
    )
    resp = TestClient(_enroll_app()).post(
        "/enroll", data={"token": tok, "api_key": "a" * 32}
    )
    assert resp.status_code == 200
    assert "saved" in resp.text.lower()


def test_enroll_post_invalid_token_rejected(monkeypatch):
    from starlette.testclient import TestClient

    monkeypatch.setenv("ZULIPCHAT_ENROLL_SECRET", SECRET)
    resp = TestClient(_enroll_app()).post(
        "/enroll", data={"token": "bad", "api_key": "a" * 32}
    )
    assert resp.status_code == 400


# --- single-use links ------------------------------------------------------


def test_used_tokens_marks_and_expires():
    import time

    ut = UsedTokens()
    assert ut.is_used("tok") is False
    ut.mark_used("tok", expiry=time.time() + 100)
    assert ut.is_used("tok") is True
    # Other tokens are unaffected.
    assert ut.is_used("other") is False


def test_used_tokens_record_expires_with_token():
    import time

    ut = UsedTokens()
    ut.mark_used("tok", expiry=time.time() - 1)  # already past
    assert ut.is_used("tok") is False  # expired record is swept


def test_enrollment_token_expiry_roundtrip(monkeypatch):
    monkeypatch.setenv("ZULIPCHAT_ENROLL_SECRET", SECRET)
    tok = mint_enrollment_token("u@x.org", secret=SECRET, ttl_seconds=900)
    exp = enrollment_token_expiry(tok)
    assert exp is not None and exp > 0
    assert enrollment_token_expiry("garbage") is None


def _post_success_app(monkeypatch):
    """Enroll app whose try_enroll always succeeds; returns (TestClient, token)."""
    from unittest.mock import AsyncMock, MagicMock

    from starlette.testclient import TestClient

    from src.zulipchat_mcp.core import enrollment_routes

    monkeypatch.setenv("ZULIPCHAT_ENROLL_SECRET", SECRET)
    tok = mint_enrollment_token("u@x.org")
    cfg = MagicMock()
    cfg.config.site = "https://z.example"
    monkeypatch.setattr(enrollment_routes, "get_config_manager", lambda: cfg)
    monkeypatch.setattr(
        enrollment_routes,
        "try_enroll",
        AsyncMock(return_value=EnrollResult(EnrollOutcome.SUCCESS, "ok")),
    )
    return TestClient(_enroll_app()), tok


def test_enroll_link_single_use_post(monkeypatch):
    client, tok = _post_success_app(monkeypatch)

    first = client.post("/enroll", data={"token": tok, "api_key": "a" * 32})
    assert first.status_code == 200
    assert "saved" in first.text.lower()

    # Same link again: rejected as already used.
    second = client.post("/enroll", data={"token": tok, "api_key": "a" * 32})
    assert second.status_code == 400
    assert "already been used" in second.text.lower()


def test_enroll_used_link_get_shows_used_page(monkeypatch):
    client, tok = _post_success_app(monkeypatch)
    client.post("/enroll", data={"token": tok, "api_key": "a" * 32})

    resp = client.get(f"/enroll?token={tok}")
    assert resp.status_code == 400
    assert "already been used" in resp.text.lower()


def test_enroll_failed_attempt_does_not_consume(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    from starlette.testclient import TestClient

    from src.zulipchat_mcp.core import enrollment_routes

    monkeypatch.setenv("ZULIPCHAT_ENROLL_SECRET", SECRET)
    tok = mint_enrollment_token("u@x.org")
    cfg = MagicMock()
    cfg.config.site = "https://z.example"
    monkeypatch.setattr(enrollment_routes, "get_config_manager", lambda: cfg)
    # First a rejection, then a success — the link must survive the rejection.
    monkeypatch.setattr(
        enrollment_routes,
        "try_enroll",
        AsyncMock(
            side_effect=[
                EnrollResult(EnrollOutcome.INVALID_KEY, "bad", remaining_tries=5),
                EnrollResult(EnrollOutcome.SUCCESS, "ok"),
            ]
        ),
    )
    client = TestClient(_enroll_app())

    bad = client.post("/enroll", data={"token": tok, "api_key": "a" * 32})
    assert bad.status_code == 200  # form re-shown with an error, link not consumed
    assert "already been used" not in bad.text.lower()

    good = client.post("/enroll", data={"token": tok, "api_key": "a" * 32})
    assert good.status_code == 200
    assert "saved" in good.text.lower()


# --- auth scopes -----------------------------------------------------------


def test_auth_scopes_default_includes_email(monkeypatch):
    from src.zulipchat_mcp.core import auth_provider

    monkeypatch.delenv("ZULIPCHAT_AUTH_SCOPES", raising=False)
    scopes = auth_provider._scopes(["openid", "email", "profile"])
    assert "email" in scopes


def test_auth_scopes_env_override(monkeypatch):
    from src.zulipchat_mcp.core import auth_provider

    monkeypatch.setenv("ZULIPCHAT_AUTH_SCOPES", "openid, email , profile extra")
    assert auth_provider._scopes(["openid"]) == ["openid", "email", "profile", "extra"]


# --- OpenBao TLS verification ---------------------------------------------


def test_secretstore_verify_uses_cacert_path():
    store = SecretStore(addr="https://bao", token="t", cacert="/certs/ca.pem")
    assert store._verify() == "/certs/ca.pem"


def test_secretstore_verify_default_true():
    store = SecretStore(addr="https://bao", token="t")
    assert store._verify() is True


def test_secretstore_verify_disabled_overrides_cacert():
    store = SecretStore(
        addr="https://bao", token="t", cacert="/certs/ca.pem", verify_tls=False
    )
    assert store._verify() is False


# --- startup self-check ----------------------------------------------------


def test_startup_required_default_false(monkeypatch):
    from src.zulipchat_mcp.core import hosted_config

    monkeypatch.delenv("OPENBAO_STARTUP_REQUIRED", raising=False)
    assert hosted_config.openbao_startup_required() is False


def test_startup_required_true(monkeypatch):
    from src.zulipchat_mcp.core import hosted_config

    monkeypatch.setenv("OPENBAO_STARTUP_REQUIRED", "1")
    assert hosted_config.openbao_startup_required() is True


async def test_selfcheck_ok_when_reachable():
    def handler(request):
        if request.url.path == "/v1/sys/health":
            return httpx.Response(200, json={"initialized": True})
        return httpx.Response(404, json={})

    store = _bao_store(handler)  # static token -> auth needs no HTTP
    assert await store.selfcheck() is True


async def test_selfcheck_false_on_connection_failure():
    def boom(request):
        raise httpx.ConnectError("down")

    store = _bao_store(boom)
    assert await store.selfcheck() is False
