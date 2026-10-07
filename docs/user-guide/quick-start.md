# Quick Start

This guide gets a first-time user from zero to a working Zulip MCP connection in about two minutes.

## 1. Get a `zuliprc`

In Zulip: `Settings` -> `Personal settings` -> `Account & privacy` -> `API key` -> `Download .zuliprc`.

Save it as `~/.zuliprc`.

## 2. Start the server

**For personal use** (full read/write access):

```bash
zulipchat-mcp --zulip-config-file ~/.zuliprc
```

**For organizational deployment** (read-only, filtered, no agents):

```bash
zulipchat-mcp --read-only --disable-agents --zulip-config-file ~/.zuliprc
```

With channel filtering, set the environment variables first — see [Configuration](configuration.md#channel-filter).

## 3. Connect a client

Example with Claude Code:

```bash
claude mcp add zulipchat -- zulipchat-mcp --read-only --disable-agents --zulip-config-file ~/.zuliprc
```

Then ask the assistant to call `server_info`.

## Optional: setup wizard

If you want an interactive flow:

```bash
zulipchat-mcp-setup
```

The wizard scans for `zuliprc` files, validates credentials against Zulip, and prints client config snippets.

## Deployment modes

| Mode | Command | Tools |
|------|---------|-------|
| Full access | `zulipchat-mcp --zulip-config-file ~/.zuliprc` | 20 core |
| Read-only | `--read-only` | 9 (search/read only) |
| No agents | `--disable-agents` | No agent tools, listener never starts |
| Extended | `--extended-tools` | 56 tools |
| Locked down | `--read-only --disable-agents` | 9 tools, no writes, no agents |

## Dual identity (user + bot)

```bash
zulipchat-mcp \
  --zulip-config-file ~/.zuliprc \
  --zulip-bot-config-file ~/.zuliprc-bot
```

The server starts as user identity. Use `switch_identity` to move between `user` and `bot`. Not available in read-only mode.

## Next

- [Configuration](configuration.md) — all CLI flags and environment variables
- [Installation](installation.md)
- [Integration docs](../integrations/README.md)
