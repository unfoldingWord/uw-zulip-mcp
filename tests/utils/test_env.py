"""Tests for the shared env_bool helper."""

import pytest

from src.zulipchat_mcp.utils.env import env_bool


def test_default_when_unset(monkeypatch):
    monkeypatch.delenv("X_FLAG", raising=False)
    assert env_bool("X_FLAG") is False
    assert env_bool("X_FLAG", True) is True


@pytest.mark.parametrize("val", ["1", "true", "True", "TRUE", "yes", "YES", "on", "On"])
def test_truthy_values(monkeypatch, val):
    monkeypatch.setenv("X_FLAG", val)
    assert env_bool("X_FLAG") is True


@pytest.mark.parametrize("val", ["0", "false", "False", "no", "off", "", "  ", "nope"])
def test_falsy_values(monkeypatch, val):
    monkeypatch.setenv("X_FLAG", val)
    assert env_bool("X_FLAG", default=True) is (val.strip() == "")
    # empty/whitespace falls back to default; everything else here is falsy
    monkeypatch.setenv("X_FLAG", val)
    assert env_bool("X_FLAG", default=False) is False


def test_whitespace_padding(monkeypatch):
    monkeypatch.setenv("X_FLAG", "  true  ")
    assert env_bool("X_FLAG") is True
