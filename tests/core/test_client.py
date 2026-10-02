"""Tests for core/client.py."""

from unittest.mock import MagicMock, patch

import pytest

from src.zulipchat_mcp.config import ConfigManager, ZulipConfig
from src.zulipchat_mcp.core.client import ZulipClientWrapper, ZulipMessage
from src.zulipchat_mcp.core.request_credentials import (
    AuthFailureSignal,
    RequestCredentials,
    bind_auth_failure_signal,
    unbind_auth_failure_signal,
)


class TestZulipClientWrapper:
    """Tests for ZulipClientWrapper."""

    @pytest.fixture
    def mock_config_manager(self):
        """Mock ConfigManager."""
        config_data = ZulipConfig(
            email="test@example.com",
            api_key="key",
            site="https://chat.zulip.org",
            bot_email="bot@example.com",
            bot_api_key="botkey",
            bot_name="Bot",
        )
        manager = MagicMock(spec=ConfigManager)
        manager.config = config_data
        manager.validate_config.return_value = True
        manager.has_bot_credentials.return_value = True

        manager.get_zulip_client_config.side_effect = lambda use_bot: {
            "email": "bot@example.com" if use_bot else "test@example.com",
            "api_key": "botkey" if use_bot else "key",
            "site": "https://chat.zulip.org",
            "config_file": None,
        }
        return manager

    @pytest.fixture
    def mock_zulip_client(self):
        """Mock underlying zulip.Client."""
        with patch("src.zulipchat_mcp.core.client.Client") as mock:
            client_instance = MagicMock()
            mock.return_value = client_instance
            yield client_instance

    def test_init_validation_failure(self):
        """Test initialization fails if config invalid."""
        manager = MagicMock(spec=ConfigManager)
        manager.validate_config.return_value = False

        with pytest.raises(ValueError, match="Invalid Zulip configuration"):
            ZulipClientWrapper(config_manager=manager)

    def test_init_user_identity(self, mock_config_manager, mock_zulip_client):
        """Test initialization with user identity."""
        wrapper = ZulipClientWrapper(
            config_manager=mock_config_manager, use_bot_identity=False
        )
        assert wrapper.identity == "user"
        assert wrapper.identity_name == "test"  # from email split
        assert wrapper.current_email == "test@example.com"

    def test_init_bot_identity(self, mock_config_manager, mock_zulip_client):
        """Test initialization with bot identity."""
        wrapper = ZulipClientWrapper(
            config_manager=mock_config_manager, use_bot_identity=True
        )
        assert wrapper.identity == "bot"
        assert wrapper.identity_name == "Bot"
        assert wrapper.current_email == "bot@example.com"

    def test_base_url_normalized_from_config_file_client(self, mock_zulip_client):
        """Test config-file client base_url strips API suffixes."""
        manager = MagicMock(spec=ConfigManager)
        manager.validate_config.return_value = True
        manager.has_bot_credentials.return_value = False
        manager.get_zulip_client_config.return_value = {
            "email": None,
            "api_key": None,
            "site": None,
            "config_file": "/tmp/zuliprc",
        }

        mock_zulip_client.base_url = "https://ai4hpc.zulipchat.com/api/v1"
        mock_zulip_client.email = "test@example.com"

        wrapper = ZulipClientWrapper(config_manager=manager)

        assert wrapper.base_url == "https://ai4hpc.zulipchat.com"

    def test_lazy_loading(self, mock_config_manager, mock_zulip_client):
        """Test client is created only when accessed."""
        wrapper = ZulipClientWrapper(config_manager=mock_config_manager)
        assert wrapper._client is None

        # Access client property
        _ = wrapper.client
        assert wrapper._client is not None

        # Verify Client constructor called with correct args
        from src.zulipchat_mcp.core.client import Client

        Client.assert_called_with(
            email="test@example.com", api_key="key", site="https://chat.zulip.org"
        )

    def test_send_message_stream(self, mock_config_manager, mock_zulip_client):
        """Test sending stream message."""
        wrapper = ZulipClientWrapper(config_manager=mock_config_manager)
        mock_zulip_client.send_message.return_value = {"result": "success", "id": 1}

        wrapper.send_message("stream", "general", "hello", "topic1")

        mock_zulip_client.send_message.assert_called_with(
            {"type": "stream", "content": "hello", "to": "general", "topic": "topic1"}
        )

    def test_send_message_private(self, mock_config_manager, mock_zulip_client):
        """Test sending private message."""
        wrapper = ZulipClientWrapper(config_manager=mock_config_manager)
        mock_zulip_client.send_message.return_value = {"result": "success", "id": 1}

        wrapper.send_message("private", "user@example.com", "hello")

        mock_zulip_client.send_message.assert_called_with(
            {"type": "private", "content": "hello", "to": ["user@example.com"]}
        )

    def test_get_messages_raw(self, mock_config_manager, mock_zulip_client):
        """Test getting raw messages."""
        wrapper = ZulipClientWrapper(config_manager=mock_config_manager)
        mock_zulip_client.get_messages.return_value = {
            "result": "success",
            "messages": [],
        }

        wrapper.get_messages_raw(anchor="newest", num_before=10)

        mock_zulip_client.get_messages.assert_called()
        args = mock_zulip_client.get_messages.call_args[0][0]
        assert args["anchor"] == "newest"
        assert args["num_before"] == 10

    def test_get_messages_typed(self, mock_config_manager, mock_zulip_client):
        """Test getting typed messages."""
        wrapper = ZulipClientWrapper(config_manager=mock_config_manager)
        mock_zulip_client.get_messages.return_value = {
            "result": "success",
            "messages": [
                {
                    "id": 1,
                    "sender_full_name": "Alice",
                    "sender_email": "alice@example.com",
                    "timestamp": 1234567890,
                    "content": "hi",
                    "type": "stream",
                    "display_recipient": "general",
                    "subject": "topic",
                }
            ],
        }

        messages = wrapper.get_messages()
        assert len(messages) == 1
        assert isinstance(messages[0], ZulipMessage)
        assert messages[0].sender_full_name == "Alice"

    def test_get_streams_caching(self, mock_config_manager, mock_zulip_client):
        """Test get_streams uses cache."""
        wrapper = ZulipClientWrapper(config_manager=mock_config_manager)

        # Setup cache
        from src.zulipchat_mcp.core.client import stream_cache

        stream_cache.set_streams([{"name": "cached"}])

        # Call should return cached
        result = wrapper.get_streams()
        assert result["streams"][0]["name"] == "cached"
        mock_zulip_client.get_streams.assert_not_called()

        # Force fresh
        mock_zulip_client.get_streams.return_value = {
            "result": "success",
            "streams": [{"name": "fresh"}],
        }
        result = wrapper.get_streams(force_fresh=True)
        assert result["streams"][0]["name"] == "fresh"
        mock_zulip_client.get_streams.assert_called()

    def test_upload_file_client_method(self, mock_config_manager, mock_zulip_client):
        """Test upload_file using client method if available."""
        wrapper = ZulipClientWrapper(config_manager=mock_config_manager)

        # Mock client having upload_file
        mock_zulip_client.upload_file.return_value = {
            "result": "success",
            "uri": "/user_uploads/file",
        }

        content = b"content"
        result = wrapper.upload_file(content, "test.txt")

        assert result["result"] == "success"
        mock_zulip_client.upload_file.assert_called()

    def test_upload_file_fallback(self, mock_config_manager, mock_zulip_client):
        """Test upload_file fallback to requests."""
        wrapper = ZulipClientWrapper(config_manager=mock_config_manager)

        # Remove upload_file from client mock
        del mock_zulip_client.upload_file

        # Mock requests.post
        # We need to make sure requests is importable even if not installed in env?
        # It is in dependencies.
        with patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"uri": "url"}

            # We need client.email and api_key set
            mock_zulip_client.email = "test@example.com"
            mock_zulip_client.api_key = "key"
            mock_zulip_client.base_url = "https://chat.zulip.org"

            # Trigger property to set _base_url in wrapper
            _ = wrapper.client

            result = wrapper.upload_file(b"data", "file.txt")
            assert result["result"] == "success"
            mock_post.assert_called()

    def test_get_daily_summary(self, mock_config_manager, mock_zulip_client):
        """Test daily summary generation."""
        wrapper = ZulipClientWrapper(config_manager=mock_config_manager)

        # Mock get_messages_from_stream
        # It calls get_messages_raw internally. We can mock get_messages_raw or get_messages_from_stream.
        # Since get_messages_from_stream is cached, let's mock it on the instance or patch class.

        with patch.object(ZulipClientWrapper, "get_messages_from_stream") as mock_get:
            mock_get.return_value = {
                "result": "success",
                "messages": [
                    {"sender_full_name": "User1", "subject": "Topic1"},
                    {"sender_full_name": "User1", "subject": "Topic1"},
                    {"sender_full_name": "User2", "subject": "Topic2"},
                ],
            }

            summary = wrapper.get_daily_summary(streams=["general"])

            assert summary["total_messages"] == 3
            assert summary["top_senders"]["User1"] == 2
            assert summary["streams"]["general"]["topics"]["Topic1"] == 2


class TestAuthFailureHook:
    """A per-request user client trips the auth-failure signal on UNAUTHORIZED."""

    def _wrapper_with_signal(self, signal, raw_client):
        """Build a credentials-based wrapper whose client is `raw_client`."""
        creds = RequestCredentials(email="u@example.com", api_key="k" * 32)
        token = bind_auth_failure_signal(signal)
        try:
            with patch("src.zulipchat_mcp.core.client.Client", return_value=raw_client):
                wrapper = ZulipClientWrapper(
                    credentials=creds, site="https://chat.example.com"
                )
                _ = wrapper.client  # force lazy creation + hook install
            return wrapper
        finally:
            unbind_auth_failure_signal(token)

    def test_trips_on_unauthorized(self):
        signal = AuthFailureSignal()
        raw = MagicMock()
        raw.do_api_query = MagicMock(
            return_value={"result": "error", "code": "UNAUTHORIZED", "msg": "bad"}
        )
        wrapper = self._wrapper_with_signal(signal, raw)

        result = wrapper.client.do_api_query({}, "users/me", method="GET")

        assert result["code"] == "UNAUTHORIZED"  # passthrough preserved
        assert signal.triggered is True

    def test_does_not_trip_on_success(self):
        signal = AuthFailureSignal()
        raw = MagicMock()
        raw.do_api_query = MagicMock(return_value={"result": "success", "id": 1})
        wrapper = self._wrapper_with_signal(signal, raw)

        wrapper.client.do_api_query({}, "messages", method="POST")

        assert signal.triggered is False

    def test_no_hook_without_signal(self):
        """No bound signal (e.g. bot/stdio client): do_api_query is untouched."""
        raw = MagicMock()
        original = MagicMock(return_value={"result": "error", "code": "UNAUTHORIZED"})
        raw.do_api_query = original
        creds = RequestCredentials(email="u@example.com", api_key="k" * 32)
        with patch("src.zulipchat_mcp.core.client.Client", return_value=raw):
            wrapper = ZulipClientWrapper(
                credentials=creds, site="https://chat.example.com"
            )
            _ = wrapper.client

        # The method was not wrapped (identity object unchanged).
        assert wrapper.client.do_api_query is original
