# Configuration

This page documents all runtime configuration for uw-zulip-mcp v0.7.1.

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
| `--extended-tools` | Register all 56 tools instead of the 20-tool core set |
| `--unsafe` | Enable destructive operations |
| `--debug` | Enable debug logging |
| `--enable-listener` | Start message listener eagerly (default: lazy) |
| `--transport MODE` | Transport: `stdio` (default), `http`, `streamable-http`, `sse` |
| `--host HOST` | Bind address for HTTP/SSE mode (default: `127.0.0.1`) |
| `--port PORT` | Listen port for HTTP/SSE mode (default: `3000`) |
| `--hosted` | OAuth2-only multi-user mode: clients authenticate with OAuth; the server resolves each user's Zulip API key from OpenBao/Vault ([details](hosted-authentication.md)) |

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
| `ZULIPCHAT_EXTENDED_TOOLS` | `false` | Register all 56 tools |

### Hosted mode & authentication

Full guide: [Hosted Mode & Authentication](hosted-authentication.md).

| Variable | Default | Description |
|----------|---------|-------------|
| `ZULIPCHAT_HOSTED` | `false` | OAuth2-only multi-user mode: clients authenticate with OAuth; the server resolves each user's Zulip API key from OpenBao/Vault. Requires `ZULIP_SITE`, an auth provider, OpenBao, and a network transport |
| `ZULIPCHAT_AUTH_MODE` | `none` | OAuth for the user→server hop: `google`, `oidc`, `jwt`, or `static` (dev only) |
| `ZULIPCHAT_AUTH_CLIENT_ID` / `ZULIPCHAT_AUTH_CLIENT_SECRET` | — | OAuth client credentials (`google`, `oidc`) |
| `ZULIPCHAT_AUTH_BASE_URL` | — | Public URL of this MCP server (`google`, `oidc`) |
| `ZULIPCHAT_AUTH_CONFIG_URL` | — | OIDC discovery URL (`oidc`) |
| `ZULIPCHAT_AUTH_JWKS_URI` / `ZULIPCHAT_AUTH_ISSUER` / `ZULIPCHAT_AUTH_AUDIENCE` | — | JWT verification (`jwt`) |
| `ZULIPCHAT_AUTH_STATIC_TOKENS` | — | Comma-separated bearer tokens (`static`, dev/test only) |
| `ZULIPCHAT_AUTH_SCOPES` | `openid email profile` | Scopes to request (`google`, `oidc`). The email scope is required — users are keyed by email |

#### OpenBao / Vault (user key store)

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENBAO_ADDR` | `http://127.0.0.1:8200` | OpenBao/Vault address |
| `OPENBAO_ROLE_ID` / `OPENBAO_SECRET_ID` | — | AppRole login (recommended) |
| `OPENBAO_TOKEN` | — | Direct token (dev/testing; bypasses AppRole) |
| `OPENBAO_KV_MOUNT` | `secret` | KV v2 mount point |
| `OPENBAO_KV_PATH` | `zulip-mcp/users` | Base path for user secrets |
| `OPENBAO_NAMESPACE` | — | Optional namespace header |
| `OPENBAO_TLS_VERIFY` | `true` | Set to `false` to disable TLS verification (dev only) |
| `OPENBAO_CACERT` | — | Path to a PEM containing the root CA and any intermediate CAs (not OpenBao's leaf cert). Use when OpenBao uses a private/internal CA |
| `OPENBAO_STARTUP_REQUIRED` | `false` | When `true`, a failed OpenBao startup self-check aborts boot (fail fast). Default: log and continue |

#### Enrollment & key cache

| Variable | Default | Description |
|----------|---------|-------------|
| `ZULIPCHAT_ENROLL_SECRET` | random per-process | HMAC secret for enrollment links; set in production |
| `ZULIPCHAT_PUBLIC_URL` | `ZULIPCHAT_AUTH_BASE_URL` | Public URL used to build enrollment links |
| `ZULIPCHAT_ENROLL_TOKEN_TTL_SECONDS` | `900` | Enrollment link lifetime |
| `ZULIPCHAT_ENROLL_MAX_ATTEMPTS` | `6` | Failed submissions before a cool-off |
| `ZULIPCHAT_ENROLL_COOLOFF_SECONDS` | `900` | Cool-off duration after too many failures |
| `ZULIPCHAT_KEY_CACHE_TTL_SECONDS` | `86400` | In-memory key cache inactivity TTL (sliding) |
| `ZULIPCHAT_REENROLL_ON_AUTH_FAILURE` | `true` | On a Zulip auth rejection, clear the stored key (cache + vault) and re-enroll |

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

### Transport

| Variable | Default | Description |
|----------|---------|-------------|
| `ZULIPCHAT_TRANSPORT` | `stdio` | Transport: `stdio`, `http`, `streamable-http`, or `sse` |
| `ZULIPCHAT_HOST` | `127.0.0.1` | Bind address for HTTP/SSE mode |
| `MCP_PORT` | `3000` | Listen port for HTTP/SSE mode (also `--port`) |

### Other

| Variable | Default | Description |
|----------|---------|-------------|
| `ZULIPCHAT_QUIET` | `false` | Suppress startup privacy notice |
| `MCP_DEBUG` | `false` | Debug logging |

## Transport modes

The server supports four transport protocols, selectable via `--transport` or `ZULIPCHAT_TRANSPORT`:

| Transport | Use case |
|-----------|----------|
| `stdio` (default) | Local use — AI client spawns the process directly |
| `http` / `streamable-http` | Persistent daemon — recommended for Docker and shared deployments |
| `sse` | Legacy SSE clients — use `http` for new deployments |

### stdio (default)

No extra flags needed. The AI client (Claude Code, Cursor, etc.) spawns the process and communicates over stdin/stdout.

```bash
zulipchat-mcp --zulip-config-file ~/.zuliprc
```

MCP client config example:
```bash
claude mcp add zulipchat -- uvx zulipchat-mcp --zulip-config-file ~/.zuliprc
```

### HTTP / streamable-HTTP (network mode)

Run as a persistent daemon. The MCP client connects over HTTP.

```bash
zulipchat-mcp --transport http --host 127.0.0.1 --port 3000 --zulip-config-file ~/.zuliprc
```

Or via environment variables:
```bash
ZULIPCHAT_TRANSPORT=http ZULIPCHAT_HOST=127.0.0.1 MCP_PORT=3000 zulipchat-mcp
```

MCP client config example:
```bash
claude mcp add zulipchat --url http://127.0.0.1:3000/mcp
```

### Docker

The Docker image defaults to `http` transport bound to `0.0.0.0:3000`.

```bash
docker run -p 3000:3000 \
  -e ZULIP_EMAIL=... -e ZULIP_API_KEY=... -e ZULIP_SITE=... \
  uw-zulip-mcp
```

Connect your MCP client to `http://localhost:3000/mcp`.

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
