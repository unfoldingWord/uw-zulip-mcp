"""Cache isolation across request identities (hosted mode).

Cached stream lists and user directories reflect what ONE user may see.
These tests prove a second identity can never read the first's entries.
"""

import pytest

from src.zulipchat_mcp.core.cache import StreamCache, UserCache
from src.zulipchat_mcp.core.request_credentials import (
    RequestCredentials,
    bind_request_credentials,
    unbind_request_credentials,
)

ALICE = RequestCredentials(email="alice@x.com", api_key="a" * 32)
BOB = RequestCredentials(email="bob@x.com", api_key="b" * 32)


class _Identity:
    def __init__(self, creds):
        self.creds = creds

    def __enter__(self):
        self.token = bind_request_credentials(self.creds)

    def __exit__(self, *exc):
        unbind_request_credentials(self.token)


class TestStreamCacheScoping:
    def test_streams_do_not_leak_across_identities(self):
        cache = StreamCache(ttl=600)
        with _Identity(ALICE):
            cache.set_streams([{"name": "private-alice-stream"}])
            assert cache.get_streams() == [{"name": "private-alice-stream"}]
        with _Identity(BOB):
            assert cache.get_streams() is None

    def test_stream_info_scoped(self):
        cache = StreamCache(ttl=600)
        with _Identity(ALICE):
            cache.set_stream_info("secret", {"invite_only": True})
        with _Identity(BOB):
            assert cache.get_stream_info("secret") is None
        with _Identity(ALICE):
            assert cache.get_stream_info("secret") == {"invite_only": True}

    def test_unscoped_local_mode_unchanged(self):
        cache = StreamCache(ttl=600)
        cache.set_streams([{"name": "general"}])
        assert cache.get_streams() == [{"name": "general"}]


class TestUserCacheScoping:
    def test_users_list_scoped(self):
        cache = UserCache(ttl=900)
        with _Identity(ALICE):
            cache.set_users([{"email": "x@x.com", "full_name": "Xavier X"}])
            assert cache.get_users() is not None
        with _Identity(BOB):
            assert cache.get_users() is None

    def test_name_index_scoped(self):
        cache = UserCache(ttl=900)
        with _Identity(ALICE):
            cache.set_users([{"email": "hidden@x.com", "full_name": "Hidden Person"}])
            assert cache.resolve_user("Hidden Person")["email"] == "hidden@x.com"
        with _Identity(BOB):
            assert cache.resolve_user("Hidden Person")["email"] is None

    def test_email_delivery_map_scoped(self):
        cache = UserCache(ttl=900)
        with _Identity(ALICE):
            cache.set_users(
                [
                    {
                        "email": "display@x.com",
                        "delivery_email": "real@x.com",
                        "full_name": "Some One",
                    }
                ]
            )
            assert cache.is_same_user("display@x.com", "real@x.com")
        with _Identity(BOB):
            assert not cache.is_same_user("display@x.com", "real@x.com")

    def test_user_info_scoped(self):
        cache = UserCache(ttl=900)
        with _Identity(ALICE):
            cache.set_user_info("p@x.com", {"role": "admin"})
        with _Identity(BOB):
            assert cache.get_user_info("p@x.com") is None


class TestGetClientCredentialInjection:
    def test_get_client_uses_request_credentials(self, monkeypatch):
        from src.zulipchat_mcp import config as config_mod

        monkeypatch.setenv("ZULIP_SITE", "https://org.zulipchat.com")
        config_mod.init_config_manager()
        with _Identity(ALICE):
            client = config_mod.get_client()
        assert client.current_email == "alice@x.com"
        assert client.identity == "user"
        assert "org.zulipchat.com" in client._base_url

    def test_get_client_requires_server_side_site(self, monkeypatch):
        from src.zulipchat_mcp import config as config_mod

        monkeypatch.delenv("ZULIP_SITE", raising=False)
        monkeypatch.delenv("ZULIP_CONFIG_FILE", raising=False)
        config_mod.init_config_manager()
        with _Identity(ALICE):
            with pytest.raises(RuntimeError, match="ZULIP_SITE"):
                config_mod.get_client()

    def test_credentials_never_reach_disk_or_config(self, monkeypatch):
        """The config singleton must not absorb request credentials."""
        from src.zulipchat_mcp import config as config_mod

        monkeypatch.setenv("ZULIP_SITE", "https://org.zulipchat.com")
        cm = config_mod.init_config_manager()
        with _Identity(ALICE):
            config_mod.get_client()
        assert cm.config.email != "alice@x.com"
        assert cm.config.api_key != "a" * 32
