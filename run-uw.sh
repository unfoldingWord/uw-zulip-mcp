#!/usr/bin/env bash
# uw-zulip-mcp launcher — loads org privacy config and starts the MCP server
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Load channel filter config
set -a
source "$SCRIPT_DIR/.env"
set +a

# Launch the MCP server (read-only, no agents)
exec uv run --directory "$SCRIPT_DIR" zulipchat-mcp \
    --read-only \
    --disable-agents \
    --zulip-config-file ~/.zuliprc
