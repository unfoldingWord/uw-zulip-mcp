# ZulipChat MCP Server

<div align="center">

  <h3>Model Context Protocol server for Zulip Chat. Connect Claude Code, Gemini CLI, Codex, Cursor, Windsurf, VS Code Copilot, and other MCP clients to Zulip.</h3>

  [![PyPI](https://img.shields.io/pypi/v/zulipchat-mcp)](https://pypi.org/project/zulipchat-mcp/)
  [![CI](https://github.com/akougkas/zulipchat-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/akougkas/zulipchat-mcp/actions/workflows/ci.yml)
  [![Publish](https://github.com/akougkas/zulipchat-mcp/actions/workflows/publish.yml/badge.svg)](https://github.com/akougkas/zulipchat-mcp/actions/workflows/publish.yml)
  [![Coverage](https://img.shields.io/badge/coverage-67%25-brightgreen)](https://github.com/akougkas/zulipchat-mcp/actions/workflows/ci.yml)
  [![Downloads](https://img.shields.io/pypi/dm/zulipchat-mcp)](https://pypi.org/project/zulipchat-mcp/)
  [![GitHub stars](https://img.shields.io/github/stars/akougkas/zulipchat-mcp)](https://github.com/akougkas/zulipchat-mcp/stargazers)
  [![Python](https://img.shields.io/pypi/pyversions/zulipchat-mcp)](https://pypi.org/project/zulipchat-mcp/)
  [![License](https://img.shields.io/github/license/akougkas/zulipchat-mcp)](LICENSE)
  [![MCP](https://img.shields.io/badge/MCP-Compatible-blue)](https://modelcontextprotocol.io)

  [Quick Start](#quick-start) · [Setup Wizard](docs/user-guide/setup-wizard.md) · [Integrations](docs/integrations/README.md) · [Two-Tier Tools](#two-tier-tool-architecture) · [Contributing](CONTRIBUTING.md)
</div>

---

## Quick Start

```bash
uvx zulipchat-mcp --zulip-config-file ~/.zuliprc
```

That's it. Your AI assistant can now read and write Zulip messages.

Need a zuliprc? **Zulip Settings > Personal > Account & privacy > API key** — download the file, save it as `~/.zuliprc`.

Interactive onboarding:

```bash
uvx zulipchat-mcp-setup
```

## What This Does

ZulipChat MCP bridges any MCP-compatible AI assistant (Claude Code, Gemini CLI, Cursor, Windsurf, etc.) to your Zulip workspace. The assistant can:

- **Send and read messages** — stream messages, DMs, replies, reactions
- **Search conversation history** — full-text search with filters for sender, stream, time range
- **Resolve people by name** — "message Jaime" just works, no hunting for formal emails
- **Switch identities** — post as yourself or as a bot, in the same session
- **Monitor activity** — search recent messages, get stream info, check who's online

## Two-Tier Tool Architecture

v0.6.0 introduced a deliberate split: **19 core tools** by default, **~55 tools** when you need more.

### Core Mode (default)

The 19 tools that cover 95% of daily use:

| Category | Tools |
|----------|-------|
| **Messaging** | `send_message`, `edit_message`, `get_message`, `add_reaction` |
| **Search** | `search_messages`, `get_streams`, `get_stream_info`, `get_stream_topics` |
| **Users** | `resolve_user`, `get_users`, `get_own_user` |
| **Agent Comms** | `teleport_chat`, `register_agent`, `agent_message`, `request_user_input`, `wait_for_response` |
| **System** | `switch_identity`, `server_info`, `manage_message_flags` |

Why 19 instead of 55+? Fewer tools means faster tool selection, lower token overhead, and less confusion for the AI. Most tasks — sending messages, searching, reacting — only need the core set.

### Extended Mode

Need scheduled messages, event queues, file uploads, analytics, or advanced search?

```bash
uvx zulipchat-mcp --zulip-config-file ~/.zuliprc --extended-tools
```

Or via environment variable:
```bash
ZULIPCHAT_EXTENDED_TOOLS=1 uvx zulipchat-mcp --zulip-config-file ~/.zuliprc
```

Extended mode adds: `toggle_reaction`, `cross_post_message`, `advanced_search`, `construct_narrow`, `get_scheduled_messages`, `manage_scheduled_message`, `register_events`, `get_events`, `listen_events`, `upload_file`, `manage_files`, `get_daily_summary`, `manage_user_mute`, `get_user`, `get_presence`, `get_user_groups`, and more.

## Installation

Full per-client setup guide: [docs/integrations/README.md](docs/integrations/README.md)

### Claude Code

```bash
claude mcp add zulipchat -- uvx zulipchat-mcp --zulip-config-file ~/.zuliprc
```

With dual identity (you + a bot):
```bash
claude mcp add zulipchat -- uvx zulipchat-mcp \
  --zulip-config-file ~/.zuliprc \
  --zulip-bot-config-file ~/.zuliprc-bot
```

### Gemini CLI

Add to `~/.gemini/settings.json` under `mcpServers`:

```json
{
  "zulipchat": {
    "command": "uvx",
    "args": ["zulipchat-mcp", "--zulip-config-file", "/path/to/.zuliprc"]
  }
}
```

### Claude Desktop / Cursor / Any MCP Client

Add to your MCP configuration:

```json
{
  "mcpServers": {
    "zulipchat": {
      "command": "uvx",
      "args": ["zulipchat-mcp", "--zulip-config-file", "/path/to/.zuliprc"]
    }
  }
}
```

### Configuration Options

| Option | Description |
|--------|-------------|
| `--zulip-config-file PATH` | Path to your zuliprc file |
| `--zulip-bot-config-file PATH` | Bot zuliprc for dual identity |
| `--extended-tools` | Register all ~55 tools instead of 19 |
| `--unsafe` | Enable administrative tools (use with caution) |
| `--debug` | Enable debug logging |

### More clients

Dedicated setup pages:

- [Gemini CLI](docs/integrations/gemini-cli.md)
- [Codex](docs/integrations/codex.md)
- [OpenCode](docs/integrations/opencode.md)
- [VS Code + GitHub Copilot](docs/integrations/vscode-copilot.md)
- [Cursor](docs/integrations/cursor.md)
- [Windsurf](docs/integrations/windsurf.md)
- [Antigravity](docs/integrations/antigravity.md)
- [Generic MCP](docs/integrations/generic.md)

## Dual Identity

Configure both a user and a bot zuliprc to let your assistant switch between identities mid-session:

```bash
uvx zulipchat-mcp \
  --zulip-config-file ~/.zuliprc \
  --zulip-bot-config-file ~/.zuliprc-bot
```

The assistant posts as **you** by default. Call `switch_identity` to post as the bot — useful for automated notifications, agent-to-agent communication, or keeping human vs. bot messages distinct.

## Real-World Examples

**"Catch me up on what happened in #engineering today"**
→ Assistant calls `search_messages` with stream + time filter, summarizes the thread.

**"Tell the team we're deploying at 3pm"**
→ Assistant calls `send_message` to #engineering with the announcement.

**"Who sent that message about the API migration?"**
→ Assistant calls `search_messages` with keywords, returns sender and context.

**"React with :thumbs_up: to Sarah's last message"**
→ Assistant calls `resolve_user` ("Sarah"), `search_messages` (sender), then `add_reaction`.

**"DM Jaime that the PR is ready"**
→ Assistant calls `teleport_chat` with fuzzy name resolution — no email needed.

## Development

```bash
git clone https://github.com/akougkas/zulipchat-mcp.git
cd zulipchat-mcp
uv sync
uv run zulipchat-mcp --zulip-config-file ~/.zuliprc
```

Run checks:
```bash
uv run pytest -q              # 566 tests, 60% coverage gate
uv run ruff check .           # Linting
uv run mypy src               # Type checking
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide, and [CLAUDE.md](CLAUDE.md) / [AGENTS.md](AGENTS.md) for AI agent instructions.

## Architecture

```
src/zulipchat_mcp/
├── core/           # Client wrapper, identity, caching, security
├── tools/          # MCP tool implementations (two-tier registration)
├── services/       # Background listener, AFK watcher
├── utils/          # Logging, DuckDB persistence, metrics
└── config.py       # config loading (zuliprc + environment fallback)
```

Built on [FastMCP](https://github.com/jlowin/fastmcp) with async-first design, [DuckDB](https://duckdb.org) for agent state persistence, and smart user/stream caching for fast fuzzy resolution.

## Channel Filter & Access Controls

For organizational deployments, restrict which Zulip channels the MCP server can access.

### Channel Filtering (Johnny Decimal)

Filter channels by their JD naming prefix (`XX` or `XX.YY`):

```env
ZULIPCHAT_CHANNEL_FILTER_ENABLED=true
ZULIPCHAT_JD_ALLOW_AREAS=01,02,14,30-99       # JD area ranges to allow
ZULIPCHAT_JD_DENY_AREAS=                        # JD area ranges to deny (overrides allow)
ZULIPCHAT_CHANNEL_INCLUDE=00.17 All unfoldingWord  # Always include these channels
ZULIPCHAT_CHANNEL_EXCLUDE=00.16 Prayer Requests    # Always exclude these channels
ZULIPCHAT_EXCLUDE_NON_JD=true                   # Exclude channels without JD prefix
ZULIPCHAT_EXCLUDE_DMS=true                      # Exclude direct messages
ZULIPCHAT_EXCLUDE_PRIVATE=true                  # Exclude private channels
ZULIPCHAT_DENY_UNKNOWN_STREAM_IDS=false         # Set true for fail-closed on unknown IDs
```

**Evaluation order:** explicit exclude > explicit include > JD deny areas > JD allow areas > non-JD default.

Filter is enforced at the client wrapper level across all access paths (stream listing, message search, send, stream-ID tools). No tool can bypass it.

### Read-Only Mode

Restrict to search and read operations only:

```bash
zulipchat-mcp --read-only --zulip-config-file ~/.zuliprc
```

Or via environment: `ZULIPCHAT_READ_ONLY=true`

In read-only mode, write tools (send, edit, react, flag, upload) are not registered.

### Disable Agent Tools

Remove all agent/autonomous operation tools:

```bash
zulipchat-mcp --disable-agents --zulip-config-file ~/.zuliprc
```

Or via environment: `ZULIPCHAT_DISABLE_AGENTS=true`

Agent tools are not registered and background services are not started.

### Audit Logging

Log which tools were invoked and which channels were accessed — without logging message content:

```env
ZULIPCHAT_AUDIT_ENABLED=true
ZULIPCHAT_AUDIT_FILE=/var/log/zulipchat-mcp-audit.log  # optional, defaults to stderr
ZULIPCHAT_AUDIT_LEVEL=INFO                              # optional
```

Audit events include: tool name, channel accessed, search query, identity, and whether the request was blocked by policy. Message content is never logged.

### Recommended Deployment

For a locked-down organizational deployment:

```bash
zulipchat-mcp --read-only --disable-agents --zulip-config-file ~/.zuliprc
```

With channel filtering configured via environment variables. The server displays a privacy notice on startup summarizing the active configuration. Suppress with `ZULIPCHAT_QUIET=true`.

## Privacy

- **No data collection** — nothing leaves your machine except Zulip API calls
- **No telemetry** — zero analytics, tracking, or usage reporting
- **Local execution** — all processing happens on your hardware
- **Credentials stay local** — API keys are never logged or transmitted beyond your Zulip server

Full policy: [PRIVACY.md](PRIVACY.md)

## License

MIT — See [LICENSE](LICENSE)

## Links

- [Documentation Index](docs/README.md)
- [Support](SUPPORT.md)
- [Security Policy](SECURITY.md)
- [Zulip API Documentation](https://zulip.com/api/)
- [Model Context Protocol](https://modelcontextprotocol.io)
- [Report Issues](https://github.com/akougkas/zulipchat-mcp/issues)
- [Discussions](https://github.com/akougkas/zulipchat-mcp/discussions)

---

<div align="center">
  <sub>Built for the Zulip community</sub>
</div>

<!-- mcp-name: io.github.akougkas/zulipchat -->
