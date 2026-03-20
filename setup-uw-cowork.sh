#!/usr/bin/env bash
# uw-zulip-mcp — Local setup for unfoldingWord org deployment
# Configures the MCP server for Claude Code / Cowork with privacy controls
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
ZULIPRC="$HOME/.zuliprc"
ENV_FILE="$REPO_DIR/.env"

echo ""
echo "============================================"
echo "  uw-zulip-mcp — Org Deployment Setup"
echo "============================================"
echo ""

# --- 1. Check prerequisites ---
if ! command -v uv &> /dev/null; then
    echo "ERROR: 'uv' not found. Install it: https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
fi

if ! command -v claude &> /dev/null; then
    echo "WARNING: 'claude' CLI not found. MCP registration will be skipped."
    echo "         Install Claude Code: https://docs.claude.com/en/docs/claude-code"
    SKIP_CLAUDE=1
else
    SKIP_CLAUDE=0
fi

# --- 2. Check zuliprc ---
if [ ! -f "$ZULIPRC" ]; then
    echo "ERROR: No .zuliprc found at $ZULIPRC"
    echo ""
    echo "Create one with your Zulip API key:"
    echo "  1. Go to unfoldingword.zulipchat.com → Settings → API Key"
    echo "  2. Create ~/.zuliprc with:"
    echo ""
    echo "     [api]"
    echo "     email=you@unfoldingword.org"
    echo "     key=YOUR_API_KEY"
    echo "     site=https://unfoldingword.zulipchat.com"
    echo ""
    exit 1
fi
echo "✓ Found .zuliprc at $ZULIPRC"

# --- 3. Create .env with channel filter config ---
cat > "$ENV_FILE" << 'ENVEOF'
# uw-zulip-mcp channel filter configuration
# See docs/configuration.md for full reference

# Enable JD taxonomy-based channel filtering
ZULIPCHAT_CHANNEL_FILTER_ENABLED=true

# Allowed JD areas (work channels only)
# 01=Knowledge Base, 02=Cohorts, 14=Infrastructure
# 30-99=Engage Benefactors, Innovation, Field Programs, Tech, Catalyzation
ZULIPCHAT_JD_ALLOW_AREAS=01,02,14,30-99

# Channels to always exclude (sensitive/personal)
ZULIPCHAT_CHANNEL_EXCLUDE=00.16 Prayer Requests,00.18 General,00.19 Family,00.20 Random,00.21 Encouragement

# Channels to always include (overrides area rules)
ZULIPCHAT_CHANNEL_INCLUDE=00.17 All unfoldingWord

# Block DMs, private channels, and non-JD channels
ZULIPCHAT_EXCLUDE_DMS=true
ZULIPCHAT_EXCLUDE_PRIVATE=true
ZULIPCHAT_EXCLUDE_NON_JD=true

# Fail-closed: block any stream ID not in the known index
ZULIPCHAT_DENY_UNKNOWN_STREAM_IDS=true

# Read-only mode (no sending/editing via MCP)
ZULIPCHAT_READ_ONLY=true

# Disable autonomous agent features
ZULIPCHAT_DISABLE_AGENTS=true

# Audit logging
ZULIPCHAT_AUDIT_ENABLED=true
ENVEOF

echo "✓ Created .env at $ENV_FILE"

# --- 4. Install dependencies ---
echo ""
echo "Installing dependencies..."
cd "$REPO_DIR"
uv sync --all-groups 2>&1 | tail -3
echo "✓ Dependencies installed"

# --- 5. Run tests ---
echo ""
echo "Running test suite..."
TEST_OUTPUT=$(uv run pytest tests/ -q --tb=line 2>&1 | tail -3)
echo "$TEST_OUTPUT"

if echo "$TEST_OUTPUT" | grep -q "failed"; then
    echo ""
    echo "WARNING: Some tests failed. Review before deploying."
else
    echo "✓ Tests passed"
fi

# --- 6. Register with Claude Code ---
if [ "$SKIP_CLAUDE" -eq 0 ]; then
    echo ""
    echo "Registering MCP server with Claude Code..."

    # Remove existing registration if present
    claude mcp remove zulipchat 2>/dev/null || true

    # Register with org deployment flags
    # Uses 'uv run' pointed at local repo so it runs the fork, not PyPI
    claude mcp add zulipchat \
        --env-file "$ENV_FILE" \
        -- \
        uv run --directory "$REPO_DIR" \
        zulipchat-mcp \
        --read-only \
        --disable-agents \
        --zulip-config-file "$ZULIPRC"

    echo "✓ Registered 'zulipchat' MCP server with Claude Code"
fi

# --- 7. Summary ---
echo ""
echo "============================================"
echo "  Setup Complete"
echo "============================================"
echo ""
echo "  MCP server:    zulipchat (read-only, agents disabled)"
echo "  Zulip config:  $ZULIPRC"
echo "  Filter config: $ENV_FILE"
echo "  Channel filter: ENABLED (JD areas 01,02,14,30-99)"
echo "  Blocked:       Prayer, Family, General, Random, Encouragement"
echo "  DMs/Private:   blocked"
echo ""
echo "  To test manually:"
echo "    cd $REPO_DIR"
echo "    source .env && uv run zulipchat-mcp --read-only --disable-agents --zulip-config-file ~/.zuliprc"
echo ""
echo "  To use in Claude Code:"
echo "    claude  (the MCP server will start automatically)"
echo ""
echo "  To use in Cowork:"
echo "    The MCP server should appear in your Cowork connectors."
echo "    If not, restart the Claude desktop app."
echo ""
