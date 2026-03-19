"""Tests for environment-configurable cache settings."""

from unittest.mock import patch

from zulipchat_mcp.core.cache import _float_env, _int_env


class TestIntEnv:
    def test_valid_value(self):
        with patch.dict("os.environ", {"TEST_KEY": "42"}):
            assert _int_env("TEST_KEY", 10) == 42

    def test_empty_uses_default(self):
        with patch.dict("os.environ", {}, clear=True):
            assert _int_env("TEST_KEY", 300) == 300

    def test_invalid_uses_default(self):
        with patch.dict("os.environ", {"TEST_KEY": "abc"}):
            assert _int_env("TEST_KEY", 300) == 300

    def test_float_string_uses_default(self):
        with patch.dict("os.environ", {"TEST_KEY": "3.14"}):
            assert _int_env("TEST_KEY", 300) == 300


class TestFloatEnv:
    def test_valid_value(self):
        with patch.dict("os.environ", {"TEST_KEY": "0.8"}):
            assert _float_env("TEST_KEY", 0.6) == 0.8

    def test_empty_uses_default(self):
        with patch.dict("os.environ", {}, clear=True):
            assert _float_env("TEST_KEY", 0.6) == 0.6

    def test_invalid_uses_default(self):
        with patch.dict("os.environ", {"TEST_KEY": "not_a_number"}):
            assert _float_env("TEST_KEY", 0.6) == 0.6

    def test_integer_string_works(self):
        with patch.dict("os.environ", {"TEST_KEY": "1"}):
            assert _float_env("TEST_KEY", 0.6) == 1.0
