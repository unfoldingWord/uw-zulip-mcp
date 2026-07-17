"""Tests for the Claude Code hook bridge."""

from pathlib import Path

from src.zulipchat_mcp.claude_hooks import (
    _build_permission_prompt,
    _permission_decision_output,
    _persist_hook_env,
)


def test_build_permission_prompt_includes_tool_details() -> None:
    prompt = _build_permission_prompt(
        {
            "tool_name": "Bash",
            "tool_input": {"command": "npm test"},
            "permission_suggestions": [{"type": "addRules"}],
        }
    )
    assert "Bash" in prompt
    assert "npm test" in prompt
    assert "Permission suggestions available: 1" in prompt


def test_permission_decision_output_allow() -> None:
    output = _permission_decision_output("approve")
    decision = output["hookSpecificOutput"]["decision"]
    assert decision["behavior"] == "allow"


def test_permission_decision_output_deny() -> None:
    output = _permission_decision_output("deny")
    decision = output["hookSpecificOutput"]["decision"]
    assert decision["behavior"] == "deny"
    assert decision["interrupt"] is False


def test_persist_hook_env(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / "claude.env"
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(env_file))

    _persist_hook_env(
        "agent-1",
        {
            "session_id": "sess-1",
            "stream_name": "Agents-Channel",
            "topic_name": "Agents/Session/project/claude/cc-123",
        },
        {"session_id": "claude-123"},
    )

    content = env_file.read_text()
    assert "ZULIPCHAT_AGENT_ID" in content
    assert "ZULIPCHAT_SESSION_ID" in content
    assert "ZULIPCHAT_CLAUDE_SESSION_ID" in content
