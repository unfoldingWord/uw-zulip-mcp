"""Tests for integrations registry CLI."""

import json
import sys

import pytest

from src.zulipchat_mcp import __version__
from src.zulipchat_mcp.integrations import registry


def _run_main(monkeypatch, args):
    monkeypatch.setattr(sys, "argv", ["zulipchat-mcp-integrate", *args])
    registry.main()


def test_list_outputs_all_clients(monkeypatch, capsys):
    """The list command should print all supported client ids."""
    _run_main(monkeypatch, ["list"])
    output = capsys.readouterr().out.strip().splitlines()
    assert output == registry.CLIENTS


def test_print_codex_includes_extended_flag(monkeypatch, capsys):
    """Codex render should be TOML and include extended flag when requested."""
    _run_main(
        monkeypatch,
        [
            "print",
            "--client",
            "codex",
            "--zulip-config-file",
            "/home/test/.zuliprc",
            "--extended-tools",
        ],
    )
    output = capsys.readouterr().out
    assert "[mcp_servers.zulipchat]" in output
    assert 'command = "uvx"' in output
    assert '"--extended-tools"' in output


def test_print_vscode_returns_servers_shape(monkeypatch, capsys):
    """VS Code render should use `servers` key with stdio type."""
    _run_main(
        monkeypatch,
        [
            "print",
            "--client",
            "vscode",
            "--zulip-config-file",
            "/home/test/.zuliprc",
        ],
    )
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert "servers" in payload
    assert payload["servers"]["zulipchat"]["type"] == "stdio"
    assert payload["servers"]["zulipchat"]["command"] == "uvx"


def test_version_flag(monkeypatch, capsys):
    """Version action should exit with code 0 and print version."""
    with pytest.raises(SystemExit) as exc:
        _run_main(monkeypatch, ["--version"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert __version__ in out


def test_export_claude_code_standalone_merges_settings(monkeypatch, capsys, tmp_path):
    """Standalone export should merge hooks and write `.claude` assets."""
    settings_dir = tmp_path / ".claude"
    settings_dir.mkdir()
    existing_settings = {
        "theme": "light",
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "startup",
                    "hooks": [{"type": "command", "command": "echo existing"}],
                }
            ]
        },
    }
    (settings_dir / "settings.json").write_text(
        json.dumps(existing_settings),
        encoding="utf-8",
    )

    _run_main(
        monkeypatch,
        [
            "export",
            "--client",
            "claude-code",
            "--mode",
            "standalone",
            "--output-dir",
            str(tmp_path),
            "--zulip-config-file",
            "/home/test/.zuliprc",
            "--zulip-bot-config-file",
            "/home/test/.zuliprc-bot",
        ],
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "success"

    settings = json.loads((settings_dir / "settings.json").read_text(encoding="utf-8"))
    assert settings["theme"] == "light"
    assert (
        settings["hooks"]["SessionStart"][0]["hooks"][0]["command"] == "echo existing"
    )
    assert "Notification" in settings["hooks"]
    assert any(
        "zulipchat-mcp-hook" in group["hooks"][0]["command"]
        for group in settings["hooks"]["PermissionRequest"]
    )
    assert (
        tmp_path / ".claude" / "skills" / "zulipchat-session-operator" / "SKILL.md"
    ).exists()
    assert (tmp_path / ".claude" / "agents" / "zulip-session-operator.md").exists()


def test_export_claude_code_plugin_writes_modern_layout(monkeypatch, capsys, tmp_path):
    """Plugin export should write Anthropic's current plugin structure."""
    _run_main(
        monkeypatch,
        [
            "export",
            "--client",
            "claude-code",
            "--mode",
            "plugin",
            "--output-dir",
            str(tmp_path),
            "--zulip-config-file",
            "/home/test/.zuliprc",
            "--zulip-bot-config-file",
            "/home/test/.zuliprc-bot",
            "--extended-tools",
        ],
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "success"

    manifest = json.loads(
        (tmp_path / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    assert manifest["name"] == "zulipchat"
    assert manifest["version"] == __version__

    mcp_config = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    assert mcp_config["mcpServers"]["zulipchat"]["type"] == "stdio"
    assert "--extended-tools" in mcp_config["mcpServers"]["zulipchat"]["args"]

    hooks = json.loads((tmp_path / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    assert "Notification" in hooks["hooks"]
    assert (tmp_path / "skills" / "zulipchat-loop" / "SKILL.md").exists()
    assert (tmp_path / "agents" / "zulip-session-operator.md").exists()
