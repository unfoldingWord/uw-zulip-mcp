# Integration Packages

This directory contains ready-to-use integration templates for major MCP clients.

Each package includes:

- `package-metadata.json`: description, icon metadata, category tags, docs links
- Client-specific config template(s)
- Optional install helper script

Some packages also include richer scaffolds. Claude Code now ships:

- standalone `.claude/` assets with hooks, skills, and subagents
- a shareable Claude plugin template
- `zulipchat-mcp-integrate export --client claude-code` for safe local export

## Clients

- `claude-code/`
- `gemini-cli/`
- `codex/`
- `opencode/`
- `vscode-copilot/`
- `cursor/`
- `windsurf/`
- `antigravity/`
- `generic/`

## Common runtime command

```bash
uvx zulipchat-mcp --zulip-config-file ~/.zuliprc
```
