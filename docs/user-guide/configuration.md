# Configuration

This page documents all runtime configuration for uw-zulip-mcp v0.7.0-uw.

## Recommended setup

For organizational deployment (read-only, filtered, no agents):

```bash
zulipchat-mcp --read-only --disable-agents --zulip-config-file ~/.zuliprc
```

With channel filtering via environment variables (see [Channel Filter](#channel-filter) below).

For personal/development use:

```bash
zulipchat-mcp --zulip-config-file ~/.zuliprc
```

## Credential sources

The server accepts either:

1. A `zuliprc` file (preferred)
2. Environment variables (`ZULIP_EMAIL`, `ZULIP_API_KEY`, `ZULIP_SITE`)

## `zuliprc` auto-discovery

If `--zulip-config-file` is not passed, the server checks:

1. `./zuliprc`
2. `~/.zuliprc`
3. `~/.config/zulip/zuliprc`

## CLI flags

```bash
zulipchat-mcp [options]
```

| Flag | Description |
|------|-------------|
| `--zulip-config-file PATH` | Path to user zuliprc |
| `--zulip-bot-config-file PATH` | Bot zuliprc for dual identity |
| `--read-only` | Search/read only — no write tools registered |
| `--disable-agents` | No agent tools, no background services |
| `--extended-tools` | Register all ~55 tools instead of 19 |
| `--unsafe` | Enable destructive operations |
| `--debug` | Enable debug logging |
| `--enable-listener` | Start message listener eagerly (default: lazy) |

## Environment variables

### Credentials

| Variable | Description |
|----------|-------------|
| `ZULIP_EMAIL` | Zulip account email |
| `ZULIP_API_KEY` | Zulip API key |
| `ZULIP_SITE` | Zulip server URL |
| `ZULIP_BOT_EMAIL` | Bot email (optional) |
| `ZULIP_BOT_API_KEY` | Bot API key (optional) |

### Config file overrides

| Variable | Description |
|----------|-------------|
| `ZULIP_CONFIG_FILE` | Path to user zuliprc |
| `ZULIP_BOT_CONFIG_FILE` | Path to bot zuliprc |

### Channel filter

| Variable | Default | Description |
|----------|---------|-------------|
| `ZULIPCHAT_CHANNEL_FILTER_ENABLED` | `false` | Master switch for channel filtering |
| `ZULIPCHAT_JD_ALLOW_AREAS` | _(empty)_ | Comma-separated JD area ranges to allow (e.g., `01,02,14,30-99`) |
| `ZULIPCHAT_JD_DENY_AREAS` | _(empty)_ | Area ranges to deny (overrides allow) |
| `ZULIPCHAT_CHANNEL_INCLUDE` | _(empty)_ | Channel names to always include (comma-separated) |
| `ZULIPCHAT_CHANNEL_EXCLUDE` | _(empty)_ | Channel names to always exclude (comma-separated, highest priority) |
| `ZULIPCHAT_EXCLUDE_NON_JD` | `true` | Exclude channels without a JD prefix |
| `ZULIPCHAT_EXCLUDE_DMS` | `true` | Exclude direct messages |
| `ZULIPCHAT_EXCLUDE_PRIVATE` | `true` | Exclude private (invite-only) channels |
| `ZULIPCHAT_DENY_UNKNOWN_STREAM_IDS` | `true` | Deny unknown stream IDs (fail-closed, set `false` to allow) |

**Evaluation order:** explicit exclude > explicit include > JD deny areas > JD allow areas > non-JD default.

**Example** (unfoldingWord deployment):
```env
ZULIPCHAT_CHANNEL_FILTER_ENABLED=true
ZULIPCHAT_JD_ALLOW_AREAS=01,02,14,30-99
ZULIPCHAT_CHANNEL_INCLUDE=00.17 All unfoldingWord
ZULIPCHAT_CHANNEL_EXCLUDE=00.16 Prayer Requests,00.18 General,00.19 Family,00.20 Random,00.21 Encouragement
ZULIPCHAT_EXCLUDE_DMS=true
ZULIPCHAT_EXCLUDE_PRIVATE=true
```

### Access control modes

| Variable | Default | Description |
|----------|---------|-------------|
| `ZULIPCHAT_READ_ONLY` | `false` | Read/search only — write tools not registered |
| `ZULIPCHAT_DISABLE_AGENTS` | `false` | Agent tools not registered, background services skipped |
| `ZULIPCHAT_EXTENDED_TOOLS` | `false` | Register all ~55 tools |

### Audit logging

| Variable | Default | Description |
|----------|---------|-------------|
| `ZULIPCHAT_AUDIT_ENABLED` | `false` | Enable structured audit logging |
| `ZULIPCHAT_AUDIT_FILE` | _(stderr)_ | Path to audit log file |
| `ZULIPCHAT_AUDIT_LEVEL` | `INFO` | Log level for audit events |

### Performance tuning

| Variable | Default | Description |
|----------|---------|-------------|
| `ZULIPCHAT_CACHE_TTL_MESSAGES` | `300` | Message cache TTL (seconds) |
| `ZULIPCHAT_CACHE_TTL_STREAMS` | `600` | Stream cache TTL (seconds) |
| `ZULIPCHAT_CACHE_TTL_USERS` | `900` | User cache TTL (seconds) |
| `ZULIPCHAT_FUZZY_MATCH_CUTOFF` | `0.6` | Name resolution threshold (0.0-1.0) |
| `ZULIPCHAT_AGENT_TIMEOUT` | `300` | Agent wait_for_response timeout (seconds) |

### Other

| Variable | Default | Description |
|----------|---------|-------------|
| `ZULIPCHAT_QUIET` | `false` | Suppress startup privacy notice |
| `MCP_DEBUG` | `false` | Debug logging |
| `MCP_PORT` | `3000` | Internal port metadata |
| `ZULIP_DEV_NOTIFY` | `false` | Bypass AFK gating for agent tools (dev only) |

## Configuration precedence

For file-path settings, environment variables are checked first, then CLI values.

For credentials, `zuliprc` is the intended primary path. Environment credentials are supported as a fallback.

## Safety model

| Layer | Control | Default |
|-------|---------|---------|
| Channel filter | JD-based access control | Disabled (all channels) |
| Read-only mode | No write tools | Disabled (read + write) |
| Agent disabling | No autonomous tools | Disabled (agents available) |
| Unsafe mode | Destructive operations | Safe (destructive ops blocked) |
| DM exclusion | No DMs to LLM | Excluded when filter enabled |
| Private exclusion | No private channels | Excluded when filter enabled |
| Audit logging | Accountability trail | Disabled |

For organizational deployment, enable the first five layers.

## Dual identity

Dual identity is optional.

```bash
zulipchat-mcp \
  --zulip-config-file ~/.zuliprc \
  --zulip-bot-config-file ~/.zuliprc-bot
```

Use `switch_identity` at runtime. Not available in read-only mode.

Bot credential files are now validated for required fields (email, key, site) at startup — not just file existence.

## Test configuration quickly

Run the server and call `server_info` from your MCP client.

## Related docs

- [Quick Start](quick-start.md)
- [Installation](installation.md)
- [Setup Wizard](setup-wizard.md)
- [Architecture](../developer-guide/architecture.md)
- [Team Overview](../uw-zulip-mcp-overview.md)
- [Security Policy](../../SECURITY.md)
