"""Tests for bot credential validation."""

import os
import tempfile

from zulipchat_mcp.config import ConfigManager


class TestBotCredentialValidation:
    def test_valid_bot_config_file(self):
        """A valid zuliprc file with all fields returns True."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".zuliprc", delete=False) as f:
            f.write("[api]\nemail=bot@example.com\nkey=abc123\nsite=https://zulip.example.com\n")
            f.flush()
            try:
                assert ConfigManager._validate_bot_config_file(f.name) is True
            finally:
                os.unlink(f.name)

    def test_missing_email_field(self):
        """Missing email field returns False."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".zuliprc", delete=False) as f:
            f.write("[api]\nkey=abc123\nsite=https://zulip.example.com\n")
            f.flush()
            try:
                assert ConfigManager._validate_bot_config_file(f.name) is False
            finally:
                os.unlink(f.name)

    def test_missing_api_section(self):
        """Missing [api] section returns False."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".zuliprc", delete=False) as f:
            f.write("[other]\nfoo=bar\n")
            f.flush()
            try:
                assert ConfigManager._validate_bot_config_file(f.name) is False
            finally:
                os.unlink(f.name)

    def test_empty_file(self):
        """Empty file returns False."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".zuliprc", delete=False) as f:
            f.write("")
            f.flush()
            try:
                assert ConfigManager._validate_bot_config_file(f.name) is False
            finally:
                os.unlink(f.name)

    def test_nonexistent_file(self):
        """Nonexistent file returns False."""
        assert ConfigManager._validate_bot_config_file("/tmp/nonexistent_zuliprc_xyz") is False
