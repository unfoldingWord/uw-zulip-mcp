# uw-zulip-mcp

unfoldingWord's fork of [zulipchat-mcp](https://github.com/akougkas/zulipchat-mcp) with privacy controls, channel filtering, and organizational deployment features.

## What This Is

An MCP server that connects AI assistants (Claude Code, Gemini CLI, Cursor, etc.) to unfoldingWord's Zulip workspace — with deterministic access controls so sensitive channels (Prayer Requests, Family, etc.) are never sent to LLM providers.

**Built on** [zulipchat-mcp v0.6.2](https://github.com/akougkas/zulipchat-mcp) (MIT licensed).

## Quick Start

### One-command setup (recommended)

```bash
./setup-uw-cowork.sh
```

This checks prerequisites, creates the `.env` with channel filter config, installs dependencies, runs tests, and registers the MCP server with Claude Code — all in one step.

### Manual start

```bash
# Load config and run
./run-uw.sh
```

Or with explicit env vars:

```bash
export ZULIPCHAT_CHANNEL_FILTER_ENABLED=true
export ZULIPCHAT_JD_ALLOW_AREAS=01,02,14,30-99
export ZULIPCHAT_CHANNEL_EXCLUDE="00.16 Prayer Requests,00.18 General,00.19 Family,00.20 Random,00.21 Encouragement"
export ZULIPCHAT_EXCLUDE_DMS=true
export ZULIPCHAT_EXCLUDE_PRIVATE=true
export ZULIPCHAT_READ_ONLY=true
export ZULIPCHAT_DISABLE_AGENTS=true

zulipchat-mcp --read-only --disable-agents --zulip-config-file ~/.zuliprc
```

## What We Changed (Fork Delta)

### Channel Filtering (Johnny Decimal)

Deterministic access control using unfoldingWord's JD naming convention. Channels are filtered by their `XX` or `XX.YY` prefix, with support for area ranges, individual overrides, and private channel exclusion.

```env
ZULIPCHAT_CHANNEL_FILTER_ENABLED=true       # Master switch
ZULIPCHAT_JD_ALLOW_AREAS=01,02,14,30-99     # JD area ranges to allow
ZULIPCHAT_JD_DENY_AREAS=                     # JD area ranges to deny (overrides allow)
ZULIPCHAT_CHANNEL_INCLUDE=00.17 All unfoldingWord  # Always include (overrides area rules)
ZULIPCHAT_CHANNEL_EXCLUDE=00.16 Prayer Requests    # Always exclude (highest priority)
ZULIPCHAT_EXCLUDE_NON_JD=true                # Channels without JD prefix excluded
ZULIPCHAT_EXCLUDE_DMS=true                   # Direct messages excluded
ZULIPCHAT_EXCLUDE_PRIVATE=true               # Private channels excluded
ZULIPCHAT_DENY_UNKNOWN_STREAM_IDS=true       # Deny unknown stream IDs (default: true)
```

**Evaluation order:** explicit exclude > explicit include > JD deny areas > JD allow areas > non-JD default.

**Enforcement:** Applied at the client wrapper level across all access paths — stream listing, message search, send, read, and stream-ID tools. No tool can bypass it.

### Read-Only Mode

```bash
zulipchat-mcp --read-only --zulip-config-file ~/.zuliprc
```

Or: `ZULIPCHAT_READ_ONLY=true`

Write tools (send, edit, react, flag, upload) are not registered at all — not just blocked but absent from the tool list.

### Agent Disabling

```bash
zulipchat-mcp --disable-agents --zulip-config-file ~/.zuliprc
```

Or: `ZULIPCHAT_DISABLE_AGENTS=true`

Agent tools are not registered and background services (message listener, scheduler) are not started.

### Audit Logging

Structured logging of tool invocations and channel access — without logging message content.

```env
ZULIPCHAT_AUDIT_ENABLED=true
ZULIPCHAT_AUDIT_FILE=/var/log/zulipchat-mcp-audit.log  # optional, defaults to stderr
ZULIPCHAT_AUDIT_LEVEL=INFO                              # optional
```

Each event is serialized as JSON via `json.dumps` (injection-safe):

```json
{"event": "tool_invocation", "tool": "search_messages", "query": "deployment status", "identity": "user", "timestamp_unix": 1710886200.123}
{"event": "channel_access", "channel": "30 Infrastructure", "access_type": "read", "identity": "user", "timestamp_unix": 1710886201.456}
{"event": "tool_invocation", "tool": "send_message", "stream": "00.16 Prayer Requests", "blocked": true, "reason": "channel_filter", "timestamp_unix": 1710886202.789}
```

### Startup Privacy Notice

On startup, the server displays a privacy notice on stderr summarizing the active configuration:

```
============================================================
  ZulipChat MCP Server — Privacy Notice
============================================================

  Messages accessed via this MCP server will be sent to
  your configured LLM provider for processing. Review your
  provider's data retention policy before use.

  Channel filter:  ENABLED
  Allowed areas:   1-2, 14-14, 30-99
  Excluded:        5 channel(s)
  Included:        1 override(s)
  Private chans:   excluded
  DMs:             excluded
  Non-JD chans:    excluded
  Read-only mode:  YES
  Agent tools:     disabled
============================================================
```

Suppress with `ZULIPCHAT_QUIET=true`.

### Configurable Cache TTLs

```env
ZULIPCHAT_CACHE_TTL_MESSAGES=300   # Message cache (default: 5 min)
ZULIPCHAT_CACHE_TTL_STREAMS=600    # Stream cache (default: 10 min)
ZULIPCHAT_CACHE_TTL_USERS=900      # User cache (default: 15 min)
ZULIPCHAT_FUZZY_MATCH_CUTOFF=0.6   # Name resolution threshold (0.0-1.0)
```

### Agent Timeout

```env
ZULIPCHAT_AGENT_TIMEOUT=300   # wait_for_response timeout in seconds (default: 300)
```

Progress is logged every 30 seconds. If running in a TTY, displays a uW branded progress indicator.

### Network Transport (SSE / HTTP)

By default the server runs over `stdio` — the AI client spawns the process directly. For Docker deployments or shared access, switch to a persistent HTTP transport.

**Local HTTP daemon** (single user, safer bind address):

```bash
zulipchat-mcp --transport http --host 127.0.0.1 --port 3000 --read-only --disable-agents --zulip-config-file ~/.zuliprc
```

Register with Claude Code:
```bash
claude mcp add zulipchat --url http://127.0.0.1:3000/mcp
```

**Docker** (binds to `0.0.0.0:3000` by default in the image):

```bash
docker run -p 3000:3000 \
  -e ZULIP_EMAIL=... \
  -e ZULIP_API_KEY=... \
  -e ZULIP_SITE=https://yourorg.zulipchat.com \
  uw-zulip-mcp
```

Or override via environment variables without rebuilding:

```bash
ZULIPCHAT_TRANSPORT=http ZULIPCHAT_HOST=0.0.0.0 MCP_PORT=3000
```

Transport choices:

| Value | Description |
|-------|-------------|
| `stdio` | Default — spawned by client, communicates over stdin/stdout |
| `http` / `streamable-http` | Persistent HTTP daemon, supports session resumption |
| `sse` | Legacy SSE — use `http` for new deployments |

### Additional Hardening

- **Bot credential validation** — `has_bot_credentials()` validates zuliprc field contents, not just file existence
- **Security scanning** — Bandit added to CI workflow
- **Silent failure fixes** — Bare `pass` in except blocks replaced with `logger.warning()` across event cleanup, service manager, and agent tracker
- **Safe env parsing** — Invalid env values degrade gracefully with warnings instead of crashing
- **Blocked-by-policy counters** — WARNING-level logging on every denied access

## Full Environment Variable Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `ZULIPCHAT_CHANNEL_FILTER_ENABLED` | `false` | Enable JD channel filtering |
| `ZULIPCHAT_JD_ALLOW_AREAS` | _(empty)_ | Comma-separated JD area ranges (e.g., `30-99`) |
| `ZULIPCHAT_JD_DENY_AREAS` | _(empty)_ | Area ranges to deny (overrides allow) |
| `ZULIPCHAT_CHANNEL_INCLUDE` | _(empty)_ | Channel names to always include |
| `ZULIPCHAT_CHANNEL_EXCLUDE` | _(empty)_ | Channel names to always exclude |
| `ZULIPCHAT_EXCLUDE_NON_JD` | `true` | Exclude channels without JD prefix |
| `ZULIPCHAT_EXCLUDE_DMS` | `true` | Exclude direct messages |
| `ZULIPCHAT_EXCLUDE_PRIVATE` | `true` | Exclude private channels |
| `ZULIPCHAT_DENY_UNKNOWN_STREAM_IDS` | `true` | Deny unknown stream IDs (fail-closed) |
| `ZULIPCHAT_READ_ONLY` | `false` | Read/search only — no write tools |
| `ZULIPCHAT_DISABLE_AGENTS` | `false` | Disable all agent tools |
| `ZULIPCHAT_AUDIT_ENABLED` | `false` | Enable audit logging |
| `ZULIPCHAT_AUDIT_FILE` | _(stderr)_ | Audit log file path |
| `ZULIPCHAT_AUDIT_LEVEL` | `INFO` | Audit log level |
| `ZULIPCHAT_AGENT_TIMEOUT` | `300` | Agent wait timeout (seconds) |
| `ZULIPCHAT_CACHE_TTL_MESSAGES` | `300` | Message cache TTL (seconds) |
| `ZULIPCHAT_CACHE_TTL_STREAMS` | `600` | Stream cache TTL (seconds) |
| `ZULIPCHAT_CACHE_TTL_USERS` | `900` | User cache TTL (seconds) |
| `ZULIPCHAT_FUZZY_MATCH_CUTOFF` | `0.6` | Fuzzy name match threshold (0.0-1.0) |
| `ZULIPCHAT_TRANSPORT` | `stdio` | Transport: `stdio`, `http`, `streamable-http`, or `sse` |
| `ZULIPCHAT_HOST` | `127.0.0.1` | Bind address for HTTP/SSE mode |
| `MCP_PORT` | `3000` | Listen port for HTTP/SSE mode |
| `ZULIPCHAT_QUIET` | `false` | Suppress startup privacy notice |

## CLI Flags

| Flag | Description |
|------|-------------|
| `--zulip-config-file PATH` | Path to user zuliprc file |
| `--zulip-bot-config-file PATH` | Bot zuliprc for dual identity |
| `--read-only` | Search/read only |
| `--disable-agents` | No agent tools or background services |
| `--extended-tools` | Register all ~55 tools instead of 19 |
| `--unsafe` | Enable administrative tools |
| `--debug` | Debug logging |
| `--enable-listener` | Start message listener eagerly |
| `--transport MODE` | Transport: `stdio` (default), `http`, `streamable-http`, `sse` |
| `--host HOST` | Bind address for HTTP/SSE mode (default: `127.0.0.1`) |
| `--port PORT` | Listen port for HTTP/SSE mode (default: `3000`) |

## Development

```bash
git clone https://github.com/unfoldingWord/uw-zulip-mcp.git
cd uw-zulip-mcp
uv sync
uv run pytest -q -m "not slow and not integration"   # 651 tests
uv run ruff check .                                   # Linting
uv run mypy src                                       # Type checking
```

### Scripts

| Script | Description |
|--------|-------------|
| `setup-uw-cowork.sh` | One-command setup — checks prereqs, creates `.env`, installs deps, runs tests, registers MCP with Claude Code |
| `run-uw.sh` | Launcher — loads `.env` and starts the server with org defaults |

### Upstream Sync

The upstream repo is tracked as a remote:

```bash
git fetch upstream
git merge upstream/main  # Review changes before merging
```

## Privacy

- **No data collection** — nothing leaves your machine except Zulip API calls
- **No telemetry** — zero analytics, tracking, or usage reporting
- **Local execution** — all processing happens on your hardware
- **Credentials stay local** — API keys are never logged or transmitted beyond your Zulip server
- **Channel filter** — sensitive channels never reach the LLM provider
- **Audit trail** — optional structured logging of all access (without message content)

## License

MIT — See [LICENSE](LICENSE)

## Upstream

Based on [akougkas/zulipchat-mcp](https://github.com/akougkas/zulipchat-mcp) v0.6.2.
