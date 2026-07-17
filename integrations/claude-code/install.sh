#!/usr/bin/env bash
set -euo pipefail

ZULIP_CONFIG_FILE="${ZULIP_CONFIG_FILE:-$HOME/.zuliprc}"
PROJECT_DIR="${1:-$PWD}"

BOT_ARGS=()
if [[ -n "${ZULIP_BOT_CONFIG_FILE:-}" ]]; then
  BOT_ARGS=(--zulip-bot-config-file "$ZULIP_BOT_CONFIG_FILE")
elif [[ -f "$HOME/.zuliprc-bot" ]]; then
  BOT_ARGS=(--zulip-bot-config-file "$HOME/.zuliprc-bot")
fi

claude mcp add zulipchat -- uvx zulipchat-mcp \
  --zulip-config-file "$ZULIP_CONFIG_FILE" \
  "${BOT_ARGS[@]}"

uv run zulipchat-mcp-integrate export \
  --client claude-code \
  --mode standalone \
  --output-dir "$PROJECT_DIR" \
  --zulip-config-file "$ZULIP_CONFIG_FILE" \
  "${BOT_ARGS[@]}"
