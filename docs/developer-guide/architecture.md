# Architecture Overview

uw-zulip-mcp v0.7.1 — unfoldingWord fork of ZulipChat MCP with privacy controls.

## Top-level modules

```text
src/zulipchat_mcp/
├── server.py          # CLI entrypoint, tool registration, startup sequence
├── config.py          # zuliprc/env config loading + identity state
├── setup_wizard.py    # interactive setup helper
├── core/
│   ├── client.py      # ZulipClientWrapper — all API calls flow through here
│   ├── channel_filter.py  # JD-based channel access control (NEW)
│   ├── audit.py       # Structured audit logging (NEW)
│   ├── progress.py    # uW branded progress indicator (NEW)
│   ├── cache.py       # TTL-based caching (message, stream, user)
│   ├── security.py    # Safety mode, rate limiting, sanitization
│   ├── identity.py    # User/bot identity management
│   ├── agent_tracker.py   # Agent registration & persistence
│   ├── service_manager.py # Background services lifecycle
│   └── ...
├── tools/             # MCP tool implementations (two-tier + mode-restricted)
├── services/          # listener/service manager
└── utils/             # logging, metrics, duckdb managers
```

## Tool registration model

`server.py` calls:

1. `register_core_tools(mcp, read_only, disable_agents)`
2. `register_extended_tools(mcp, read_only, disable_agents)` only with `--extended-tools`

Tool registration respects two mode flags:

- **`read_only=True`** — Only search/read tools are registered. Write tools (send, edit, react, flag, upload) are omitted entirely.
- **`disable_agents=True`** — Agent tools (register, sessions, message, wait) are omitted. The message listener never starts because no registered tool triggers it.

This produces:

| Mode | Tool count |
|------|-----------|
| Core (default) | 20 |
| Core + read-only | 9 |
| Core + read-only + no agents | 9 |
| Extended | 56 |
| Extended + read-only | 24 |

## Channel filter architecture

The channel filter (`core/channel_filter.py`) is the primary privacy control:

```
┌─────────────────────────────────────────────┐
│              ChannelFilter                  │
│                                             │
│  Config:                                    │
│    jd_allow_areas = [(30,99), (1,2), ...]  │
│    channel_exclude = {"00.16 Prayer..."}   │
│    exclude_private = True                   │
│    exclude_dms = True                       │
│                                             │
│  Stream Index:                              │
│    id -> {name, invite_only}               │
│                                             │
│  Methods:                                   │
│    is_channel_allowed(name)                │
│    is_channel_allowed_with_privacy(name)   │
│    is_stream_id_allowed(id)               │
│    filter_streams(list)                    │
│    filter_messages(list)                   │
└─────────────────────────────────────────────┘
```

**Enforcement points in `client.py`:**

| Method | Guard |
|--------|-------|
| `get_streams()` | `filter_streams()` on results (cached + fresh) |
| `get_messages_raw()` | `filter_messages()` on results |
| `get_messages_from_stream()` | `is_channel_allowed()` at entry |
| `send_message()` | `is_channel_allowed_with_privacy()` + DM check |
| `get_stream_topics()` | `is_stream_id_allowed()` |
| `get_subscribers()` | `is_stream_id_allowed()` |

The stream metadata index (`id -> name, invite_only`) is populated from `get_streams()` results *before* filtering, so blocked stream IDs are still known for enforcement even though they don't appear in tool output.

## Audit logging architecture

`core/audit.py` provides a dedicated `zulipchat_mcp.audit` logger:

- Serializes all events via `json.dumps` (injection-safe)
- Logs: tool name, channel, search query, identity, blocked status
- Never logs message content
- Configurable output file and log level
- Idempotent initialization

Audit hooks are wired into `client.py` at: `send_message`, `search_messages`, `get_messages_from_stream`, `get_stream_topics`.

## Startup flow

1. Parse CLI flags (`--read-only`, `--disable-agents`, `--extended-tools`, etc.).
2. Initialize config manager.
3. Validate credentials (`zuliprc` or env fallback).
4. Set unsafe-mode context.
5. **Initialize audit logging.** *(new)*
6. **Initialize channel filter** (with env validation). *(new)*
7. Initialize optional database/services (**skipped if agents disabled**).
8. Register tools (**respecting read-only and agent-disable flags**).
9. Warm user/stream caches (**populates channel filter stream index**).
10. **Display privacy notice on stderr.** *(new)*
11. Run FastMCP stdio server.

## Identity model

- Runtime identity is global (`user` or `bot`), managed in `config.py`.
- Default identity is `user`.
- `switch_identity` updates the active identity (**not available in read-only mode**).
- Bot identity is available only when bot credentials are configured.
- Bot credential validation now checks zuliprc field contents (email, key, site), not just file existence.

## Service behavior

- Listener services start through `ServiceManager`, managed by the FastMCP lifespan (eager with `--enable-listener`, otherwise lazy on first agent tool call).
- **With `--disable-agents`, no agent tools are registered, so the listener never starts.**
- Inbound topic messages are classified into session events by the agent control plane.
- `wait_for_response` has a configurable timeout (`ZULIPCHAT_AGENT_TIMEOUT`, default 300s).

## Security-related boundaries

- `--unsafe` is off by default.
- **`--read-only` prevents all write operations** (tools not registered).
- **`--disable-agents` prevents autonomous behavior** (tools not registered, services not started).
- **Channel filter prevents access to excluded channels** (enforced at client wrapper).
- **Private channels excluded by default** when filter is enabled.
- **DMs excluded by default** when filter is enabled.
- Destructive topic delete path is guarded in `agents_channel_topic_ops`.
- Agent emoji usage is validated against a fixed approved list.
- Bandit security scanning in CI.

## Caching

Cache TTLs are configurable via environment variables:

| Cache | Default | Env var |
|-------|---------|---------|
| Messages | 300s | `ZULIPCHAT_CACHE_TTL_MESSAGES` |
| Streams | 600s | `ZULIPCHAT_CACHE_TTL_STREAMS` |
| Users | 900s | `ZULIPCHAT_CACHE_TTL_USERS` |
| Fuzzy match cutoff | 0.6 | `ZULIPCHAT_FUZZY_MATCH_CUTOFF` |

Invalid env values degrade gracefully with a warning log and default fallback.
