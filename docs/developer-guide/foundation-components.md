# Foundation Components

## Configuration (`config.py`)

- Loads `.env` from current working directory when present.
- Supports `zuliprc` file path discovery and explicit paths.
- Maintains current identity (`user` or `bot`).
- Exposes `get_client()` and `get_bot_client()` wrappers.
- Bot credential validation checks zuliprc field contents (email, key, site), not just file existence.

## Client wrapper (`core/client.py`)

- Wraps Zulip Python client with convenience methods.
- Handles identity-specific credential selection.
- Provides cached `get_users()` and `get_streams()` paths.
- **Channel filter enforcement** — all access paths (stream listing, message search/read, send, stream-ID tools) are guarded by the channel filter.
- **Audit logging hooks** — tool invocations and channel access are logged at key methods.

## Channel filter (`core/channel_filter.py`) *(new in v0.7.0-uw)*

- Johnny Decimal prefix parsing (`XX` and `XX.YY` formats).
- Area-range allowlist/denylist with individual channel overrides.
- Private channel and DM exclusion.
- Stream metadata index (`id -> name, invite_only`) for ID-based enforcement.
- Configurable via environment variables.
- Module-level singleton pattern (matches existing codebase conventions).

## Audit logging (`core/audit.py`) *(new in v0.7.0-uw)*

- Dedicated `zulipchat_mcp.audit` logger (routable independently from app logs).
- All events serialized via `json.dumps` (injection-safe).
- Logs: tool name, channel, search query, identity, blocked status, timestamps.
- Never logs message content.
- Configurable output file and log level.
- Idempotent initialization.

## Progress indicator (`core/progress.py`) *(new in v0.7.0-uw)*

- uW branded ASCII art progress animation for `wait_for_response`.
- White-to-cerulean color gradient transition.
- TTY detection — no-op in non-TTY environments.
- Background thread, cursor hide/show with cleanup guarantees.

## Caching (`core/cache.py`)

- User and stream caches are used for fast fuzzy resolution.
- Startup warms both caches in `server.py`.
- **TTLs configurable** via `ZULIPCHAT_CACHE_TTL_*` env vars (default: 300s/600s/900s).
- **Fuzzy match cutoff configurable** via `ZULIPCHAT_FUZZY_MATCH_CUTOFF` (default: 0.6, clamped to 0.0-1.0).
- Invalid env values degrade gracefully with warning log and default fallback.

## Security helpers (`core/security.py`)

- Stores unsafe-mode context flag.
- Provides validation/sanitization helpers.
- Includes optional rate-limiter primitives.

## Error handling (`core/error_handling.py`)

- Retry helpers and async rate-limiter primitives.
- Shared wrappers for robust tool-side calls where used.

## Services (`core/service_manager.py`, `services/`)

- Listener startup/supervision lives in the service layer, managed by the FastMCP lifespan.
- Agent communication tooling uses persistent DuckDB-backed state shared with the agent control plane (`core/agent_control.py`).
- **With `--disable-agents`, no agent tools are registered, so the listener never starts.**
- Silent failure paths now log warnings instead of bare `pass`.

## Tool registration (`tools/__init__.py`)

- `register_core_tools(mcp, read_only, disable_agents)` defines the tool baseline.
- `register_extended_tools(mcp, read_only, disable_agents)` appends the extended tool set.
- **`read_only=True`** omits all write tools (send, edit, react, flag, upload, identity switch).
- **`disable_agents=True`** omits all agent tools (register, sessions, message, wait, events).
