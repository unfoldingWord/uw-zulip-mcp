# uw-zulip-mcp Documentation

uw-zulip-mcp v0.7.0-uw — unfoldingWord fork of ZulipChat MCP with privacy controls.

## Start Here

- [Team Overview](uw-zulip-mcp-overview.md) — what we built, why, and how to use it
- [Quick Start](user-guide/quick-start.md)
- [Installation](user-guide/installation.md)
- [Configuration](user-guide/configuration.md) — all CLI flags and environment variables
- [Setup Wizard](user-guide/setup-wizard.md)
- [Troubleshooting](TROUBLESHOOTING.md)

## Privacy & Access Controls (v0.7.0-uw)

- **Channel filtering** — JD taxonomy-based access control ([Configuration](user-guide/configuration.md#channel-filter))
- **Read-only mode** — `--read-only` ([Configuration](user-guide/configuration.md#access-control-modes))
- **Agent disabling** — `--disable-agents` ([Configuration](user-guide/configuration.md#access-control-modes))
- **Audit logging** — structured JSON trail ([Configuration](user-guide/configuration.md#audit-logging))
- **Safety model** — layered controls ([Configuration](user-guide/configuration.md#safety-model))

## Integrations

- [Integration Index](integrations/README.md)
- [Claude Code](integrations/claude-code.md)
- [Gemini CLI](integrations/gemini-cli.md)
- [Codex](integrations/codex.md)
- [OpenCode](integrations/opencode.md)
- [VS Code + GitHub Copilot](integrations/vscode-copilot.md)
- [Cursor](integrations/cursor.md)
- [Windsurf](integrations/windsurf.md)
- [Antigravity](integrations/antigravity.md)
- [Generic MCP Client](integrations/generic.md)

## API Reference

- [Messaging](api-reference/messaging.md)
- [Streams](api-reference/streams.md)
- [Users](api-reference/users.md)
- [Search](api-reference/search.md)
- [Events](api-reference/events.md)
- [Files](api-reference/files.md)
- [Agents](api-reference/agents.md)
- [Commands](api-reference/commands.md)
- [System](api-reference/system.md)

## Developer Docs

- [Architecture](developer-guide/architecture.md) — module layout, filter design, startup flow
- [Tool Categories](developer-guide/tool-categories.md)
- [Foundation Components](developer-guide/foundation-components.md)
- [Testing Guide](testing/README.md)

## Tool Modes

| Mode | Tools | Flag |
|------|-------|------|
| Core (default) | 19 | _(none)_ |
| Core + read-only | 9 | `--read-only` |
| Extended | ~55 | `--extended-tools` |
| Extended + read-only | ~25 | `--extended-tools --read-only` |

## Community and Security

- [Security Policy](../SECURITY.md)
- [Contributing Guide](../CONTRIBUTING.md)
- [Support](../SUPPORT.md)

## Release History

- [v0.7.0-uw](../CHANGELOG.md) — unfoldingWord fork (current)
- `docs/releases/` contains historical snapshots for earlier versions.
