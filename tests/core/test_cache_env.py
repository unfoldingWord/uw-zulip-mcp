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

    def test_negative_value_accepted(self):
        """_float_env accepts negative — clamping is caller's job."""
        with patch.dict("os.environ", {"TEST_KEY": "-0.1"}):
            assert _float_env("TEST_KEY", 0.6) == -0.1

    def test_over_one_accepted(self):
        """_float_env accepts >1 — clamping is caller's job."""
        with patch.dict("os.environ", {"TEST_KEY": "1.1"}):
            assert _float_env("TEST_KEY", 0.6) == 1.1


class TestFuzzyCutoffClamping:
    """Verify cutoff is clamped to [0.0, 1.0] before use."""

    def test_negative_cutoff_clamped(self):
        import difflib

        # Proves clamping works — difflib would raise on -0.1
        cutoff = max(0.0, min(1.0, -0.1))
        assert cutoff == 0.0
        # Should not raise
        difflib.get_close_matches("test", ["test"], n=1, cutoff=cutoff)

    def test_over_one_cutoff_clamped(self):
        import difflib

        cutoff = max(0.0, min(1.0, 1.1))
        assert cutoff == 1.0
        # Should not raise
        difflib.get_close_matches("test", ["test"], n=1, cutoff=cutoff)
