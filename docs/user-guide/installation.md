# Installation

This is a private fork. Install from the GitHub repository (not PyPI).

## Install from GitHub

```bash
uvx --from git+https://github.com/unfoldingWord/uw-zulip-mcp.git zulipchat-mcp --zulip-config-file ~/.zuliprc
```

## Local development install

```bash
git clone https://github.com/unfoldingWord/uw-zulip-mcp.git
cd uw-zulip-mcp
uv sync
uv run zulipchat-mcp --read-only --disable-agents --zulip-config-file ~/.zuliprc
```

## Per-client setup

Use the dedicated integration pages:

- [Claude Code](../integrations/claude-code.md)
- [Gemini CLI](../integrations/gemini-cli.md)
- [Codex](../integrations/codex.md)
- [OpenCode](../integrations/opencode.md)
- [VS Code + GitHub Copilot](../integrations/vscode-copilot.md)
- [Cursor](../integrations/cursor.md)
- [Windsurf](../integrations/windsurf.md)
- [Antigravity](../integrations/antigravity.md)
- [Generic MCP](../integrations/generic.md)

## Verify installation

```bash
zulipchat-mcp --help
```

## Upgrade

Pull latest and reinstall:

```bash
cd uw-zulip-mcp
git pull origin develop
uv sync
```

Or via uvx:

```bash
uvx --refresh --from git+https://github.com/unfoldingWord/uw-zulip-mcp.git zulipchat-mcp --help
```
