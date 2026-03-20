# uw-zulip-mcp — What We Built

## The Problem

Connecting Zulip to Claude via MCP means conversation data gets sent to Anthropic for processing. Our Zulip contains prayer requests, family news, birthdays, internal strategy — content that should never leave the organization. We needed deterministic controls, not just trust.

## The Solution

We forked [zulipchat-mcp](https://github.com/akougkas/zulipchat-mcp) (v0.6.2, MIT licensed) and added privacy-first access controls that leverage our existing Johnny Decimal naming convention.

## What It Does

**Search and summarize Zulip conversations from Claude** — but only the channels you've approved.

```
"Catch me up on what happened in 84 BT Servant today"
"Search for discussions about the Indonesia program"
"What did the infrastructure team decide about deployment?"
```

## What We Added

### 1. Channel Filter (Johnny Decimal)

Our JD naming convention (`XX` or `XX.YY` prefix on every channel) gives us a structural taxonomy to filter on. The MCP server parses channel names and enforces access rules:

- **Work channels allowed:** Areas 01, 02, 14, 30-99 (Knowledge base, Cohorts, Infrastructure, Engage Benefactors, Innovation, Field Programs, Tech, Catalyzation)
- **Sensitive channels blocked:** 00.16 Prayer Requests, 00.18 General, 00.19 Family, 00.20 Random, 00.21 Encouragement
- **Private channels blocked:** All channels with the lock icon
- **DMs blocked:** No direct messages sent to Anthropic
- **Non-JD channels blocked:** Anything without a JD prefix excluded by default

This is enforced at the API layer — no tool can bypass it. New channels automatically follow the rules based on their JD prefix.

### 2. Read-Only Mode

For the org-wide deployment, we restrict to search and read only. No sending messages, editing, reacting, or uploading files through the MCP connection.

### 3. Agent Disabling

The upstream project has autonomous agent features (register bots, send automated messages, AFK mode). We disable these entirely for org deployment — no background services, no persistent agents.

### 4. Audit Logging

Every tool invocation is logged as structured JSON: which tool, which channel, what search query, whether it was blocked. Message content is never logged. This gives us an accountability trail.

### 5. Startup Privacy Notice

When the server starts, it displays a clear summary of what's filtered and what isn't — so the operator knows exactly what data can flow to the LLM provider.

## How It's Configured

All controls are environment variables — no code changes needed to adjust policy:

| Control | Variable | Our Setting |
|---------|----------|-------------|
| Enable filtering | `ZULIPCHAT_CHANNEL_FILTER_ENABLED` | `true` |
| Allowed JD areas | `ZULIPCHAT_JD_ALLOW_AREAS` | `01,02,14,30-99` |
| Excluded channels | `ZULIPCHAT_CHANNEL_EXCLUDE` | Prayer, Family, General, Random, Encouragement |
| Included overrides | `ZULIPCHAT_CHANNEL_INCLUDE` | `00.17 All unfoldingWord` |
| Block DMs | `ZULIPCHAT_EXCLUDE_DMS` | `true` |
| Block private | `ZULIPCHAT_EXCLUDE_PRIVATE` | `true` |
| Read-only | `ZULIPCHAT_READ_ONLY` | `true` |
| No agents | `ZULIPCHAT_DISABLE_AGENTS` | `true` |
| Audit trail | `ZULIPCHAT_AUDIT_ENABLED` | `true` |

## What Anthropic Sees

With our configuration, Anthropic receives:

- Messages from **work channels only** (Infrastructure, Tech & SLR, Field Programs, Cohorts, etc.)
- **Search queries** you type (e.g., "find discussions about deployment")
- **No** prayer requests, family news, birthdays, or personal messages
- **No** DMs or private channel content
- **No** messages sent on your behalf (read-only)

Per [Anthropic's policy](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data), data is retained for 30 days for safety review, then deleted.

## Technical Details

- **651 tests** covering all filter logic, enforcement paths, injection safety, and edge cases
- **Reviewed** by automated code review with P0/P1/P2 findings addressed
- **All access paths guarded:** stream listing, message search, message send, stream-by-ID tools, subscriber lookups
- **Fail-closed option:** `ZULIPCHAT_DENY_UNKNOWN_STREAM_IDS=true` blocks any stream ID not in the known index
- **Dependencies updated:** 77 packages brought to latest (fastmcp 3.1.1, duckdb 1.5.0, pydantic 2.12, zulip 0.9.1)
- **Security scanning:** Bandit integrated into CI

## Deployment Options

### Personal use (full access)
```bash
zulipchat-mcp --zulip-config-file ~/.zuliprc
```

### Org deployment (locked down)
```bash
zulipchat-mcp --read-only --disable-agents --zulip-config-file ~/.zuliprc
```
With channel filter env vars configured.

### Claude Code integration
```bash
claude mcp add zulipchat -- zulipchat-mcp --read-only --disable-agents --zulip-config-file ~/.zuliprc
```

## Repository

[unfoldingWord/uw-zulip-mcp](https://github.com/unfoldingWord/uw-zulip-mcp) (private)

Based on [akougkas/zulipchat-mcp](https://github.com/akougkas/zulipchat-mcp) v0.6.2 (MIT).
