# Troubleshooting

## Server fails with "Invalid configuration"

- Confirm `--zulip-config-file` points to an existing file.
- If omitted, verify one of these exists:
  - `./zuliprc`
  - `~/.zuliprc`
  - `~/.config/zulip/zuliprc`
- Or provide env fallback: `ZULIP_EMAIL`, `ZULIP_API_KEY`, `ZULIP_SITE`.

## 401 Unauthorized

- Regenerate API key in Zulip personal settings.
- Ensure the key/email belongs to the same Zulip realm as `site`.
- Re-test by running setup wizard validation:

```bash
uvx --from zulipchat-mcp zulipchat-mcp-setup
```

## Bot identity cannot be selected

- Provide `--zulip-bot-config-file` or bot env credentials.
- Call `server_info` to confirm bot availability.

## Tool not found in client

- You are likely in core mode.
- Start with `--extended-tools` (or `ZULIPCHAT_EXTENDED_TOOLS=1`) for full tool set.

## `request_user_input` or approvals never resolve

- Ensure the message listener is running. It lazy-starts on the first request-wait or event-poll call.
- Confirm the reply happened in the bound session topic, not a different topic or DM.
- Confirm the reply came from the configured owner account.

## Claude hook bridge does nothing

- Make sure you installed the hook entrypoint: `zulipchat-mcp-hook`.
- Confirm Claude Code hooks are invoking the bridge with the same Zulip config files as the MCP server.
- For `SessionEnd` hooks, increase `CLAUDE_CODE_SESSIONEND_HOOKS_TIMEOUT_MS` if you need more than Claude Code’s short default timeout.

## Session messages say "Not authorized"

- Owner policy is per session topic. Only the configured owner email can steer or approve a bound session by default.
- If the bot is in a broader channel, unauthorized users can still mention it normally outside a bound session topic; the restriction applies to the bound control topic.

## Event queue errors

- Re-register using `register_events`.
- Validate `queue_id` and `last_event_id` sequence.

## File download/share failures

- Verify the file identifier is a valid upload path or full URL.
- Ensure the active identity has access to the underlying stream/DM context.

## Setup wizard EOF in non-interactive shells

The wizard is interactive. Run it directly in a terminal (no piped stdin):

```bash
uvx --from zulipchat-mcp zulipchat-mcp-setup
```

## Channel filter configuration error at startup

If the server exits with `Channel filter configuration error`, an env var has a malformed value:

- Check `ZULIPCHAT_JD_ALLOW_AREAS` and `ZULIPCHAT_JD_DENY_AREAS` — must be comma-separated numbers or ranges (e.g., `30-99,01,02`).
- Invalid examples: `abc`, `30-`, `-99`.

## Channel is not accessible (filtered)

If a tool returns "outside the configured channel filter scope":

- The channel is excluded by the JD filter configuration.
- Check `ZULIPCHAT_CHANNEL_EXCLUDE` — the channel may be explicitly excluded.
- Check `ZULIPCHAT_JD_ALLOW_AREAS` — the channel's JD area may not be in the allowed range.
- If the channel has no JD prefix and `ZULIPCHAT_EXCLUDE_NON_JD=true`, it's excluded by default.
- Private channels are excluded when `ZULIPCHAT_EXCLUDE_PRIVATE=true`.

To debug, check the startup privacy notice (stderr) which lists the active filter configuration.

## Tool not found — read-only or agents disabled

If a write tool (send_message, edit_message, etc.) is not available:

- The server may be running with `--read-only` or `ZULIPCHAT_READ_ONLY=true`.

If agent tools (register_agent, wait_for_response, etc.) are not available:

- The server may be running with `--disable-agents` or `ZULIPCHAT_DISABLE_AGENTS=true`.

Call `server_info` to check active mode.

## Bot credential validation failure

If `has_bot_credentials` returns false despite having a bot config file:

- The file must contain an `[api]` section with `email`, `key`, and `site` fields.
- Empty or malformed zuliprc files are now rejected at startup.

## Audit log not appearing

- Verify `ZULIPCHAT_AUDIT_ENABLED=true` is set.
- If using `ZULIPCHAT_AUDIT_FILE`, check the path is writable.
- Audit logs go to stderr by default (not stdout, which is MCP transport).

## More help

- [Quick Start](user-guide/quick-start.md)
- [Configuration](user-guide/configuration.md)
- [Integration docs](integrations/README.md)
- [Support](../SUPPORT.md)
