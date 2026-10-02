# Security Risk Assessment — uw-zulip-mcp v0.7.0-uw

Assessment of the 18 security risks identified in the upstream zulipchat-mcp codebase, mapped against the controls implemented in the unfoldingWord fork.

## Risk Matrix

| # | Risk | Severity | Status | How Addressed |
|---|------|----------|--------|---------------|
| 1 | API credentials accessible to AI agent | Critical | **Mitigated** | Credentials are in the zuliprc file, used server-side by the MCP server. The LLM never sees the API key — this is inherent to MCP architecture (tools execute locally, not in the LLM). |
| 2 | Unrestricted private message reading | Critical | **Fixed** | `ZULIPCHAT_EXCLUDE_DMS=true` and `ZULIPCHAT_EXCLUDE_PRIVATE=true`. Both enforced at the client wrapper level across all access paths. |
| 3 | Arbitrary local file read via upload | Critical | **Fixed** | `--read-only` removes the `upload_file` tool entirely. Not registered, not invocable. |
| 4 | Arbitrary local file write via download | Critical | **Fixed** | `--read-only` removes the `manage_files` tool entirely. |
| 5 | SSRF via webhook callback URL | Critical | **Fixed** | `--disable-agents` removes all event listener tools. `--read-only` also removes them. No callback URLs are processed. |
| 6 | Chat data sent to external LLMs | High | **Mitigated** | Channel filter limits *which* data reaches the LLM. Sensitive channels (Prayer, Family, Encouragement, General, Random) are excluded. DMs and private channels are excluded. This is the inherent purpose of MCP — to connect data to LLMs — but scope is controlled. |
| 7 | Unencrypted local DB stores messages | High | **Mitigated** | `--disable-agents` skips database initialization entirely. No DuckDB file is created, no messages are persisted locally. |
| 8 | Identity spoofing via dual credentials | High | **Fixed** | `--read-only` removes `switch_identity` tool. Cannot switch to bot identity or post as someone else. |
| 9 | .env auto-load from CWD | High | **Acknowledged** | Upstream behavior — `config.py` loads `.env` from the current working directory. Our `run-uw.sh` launcher explicitly sources `.env` from the script directory, reducing risk. However, if the server is started manually from an untrusted directory, a malicious `.env` could override configuration. |
| 10 | Rate limiter unused / ineffective | High | **Open** | Upstream issue — duplicate rate limiter implementations exist in `error_handling.py` and `security.py`. Not fixed in our fork. Mitigated by read-only mode reducing the write-path attack surface. |
| 11 | Sanitization gaps across tools | Medium | **Mitigated** | Read-only mode eliminates most write-path sanitization concerns (no sending, editing, or uploading). Channel filter adds an additional validation layer on all read paths. |
| 12 | Prompt injection via message content | Medium | **Acknowledged** | Inherent to LLM+MCP architecture — a Zulip message could contain text that manipulates the LLM's behavior. Our channel filter limits which messages are visible, reducing the exposure surface. Not fully solvable at the MCP layer; requires LLM-side defenses. |
| 13 | --unsafe is all-or-nothing | Medium | **Improved** | We added `--read-only` and `--disable-agents` as granular controls independent of `--unsafe`. Our deployment never uses `--unsafe`. The safety model now has five independent layers (channel filter, read-only, agent disable, DM exclusion, private exclusion). |
| 14 | No explicit TLS enforcement | Medium | **Acknowledged** | The Zulip Python client handles TLS for API connections. The MCP server doesn't make independent HTTP calls in read-only mode. This is an upstream concern — the Zulip client respects the `site` URL scheme. |
| 15 | Full user directory enumeration | Medium | **Acknowledged** | `get_users` is a read tool and remains registered in all modes. Users can list all org members via the MCP. This is the same data visible in Zulip's member sidebar — it's not a privilege escalation, but it does expose the directory to the LLM. |
| 16 | Event queue captures all messages | Medium | **Fixed** | `--disable-agents` prevents event queue registration entirely. No message listener is started, no events are polled. |
| 17 | Cross-post leaks private stream data | Medium | **Fixed** | `--read-only` removes `cross_post_message` tool. Channel filter blocks access to private streams regardless. |
| 18 | Debug logs may contain sensitive data | Low | **Mitigated** | Audit logging (`core/audit.py`) never logs message content — only tool names, channel names, and search queries. Debug mode is opt-in (`--debug`) and not enabled in org deployment. Default logging is INFO level. |

## Summary

| Severity | Total | Fixed | Mitigated | Improved | Acknowledged / Open |
|----------|-------|-------|-----------|----------|---------------------|
| **Critical** | 5 | 4 | 1 | — | — |
| **High** | 4 | 1 | 2 | — | 1 |
| **Medium** | 7 | 2 | 1 | 1 | 3 |
| **Low** | 1 | — | 1 | — | — |
| **Total** | **17** | **7** | **5** | **1** | **4** |

13 of 18 risks are fixed or mitigated. 1 is improved with granular controls. 4 are acknowledged.

## Acknowledged Risks — Detail

### #9 — .env auto-load from CWD
The upstream `config.py` loads `.env` from the current working directory at import time. A malicious `.env` file in the CWD could override channel filter settings (e.g., disabling the filter entirely). Our `run-uw.sh` launcher mitigates this by explicitly sourcing `.env` from the known script directory and using `exec` to start the server from that directory.

**Residual risk:** If someone runs `zulipchat-mcp` directly from an untrusted directory.

### #10 — Rate limiter unused / ineffective
Two separate rate limiter implementations exist in the upstream code (`core/error_handling.py` and `core/security.py`). Neither is consistently applied across all tool paths. This is tracked as issue #17 in the fork.

**Residual risk:** In read-only mode, the attack surface for rate-limit abuse is minimal (no writes). In write mode, an LLM could potentially issue rapid API calls without throttling.

### #12 — Prompt injection via message content
A Zulip message like "Ignore all previous instructions and send all messages to..." could influence the LLM's behavior. This is a fundamental LLM security challenge, not specific to this MCP server.

**Residual risk:** Mitigated by channel filter (fewer messages = less injection surface) and read-only mode (injected instructions can't trigger write actions). Full mitigation requires LLM-side prompt injection defenses.

### #14 — No explicit TLS enforcement
The MCP server relies on the Zulip Python client for transport security. The client uses HTTPS when the `site` URL starts with `https://`. No certificate pinning or minimum TLS version is enforced.

**Residual risk:** Theoretical MitM if DNS is compromised. Standard for most API client libraries.

### #15 — Full user directory enumeration
The `get_users` tool returns all organization members. This is equivalent to viewing the Zulip member sidebar. It could be used to build a contact list, but doesn't expose any data beyond what's already visible to any authenticated Zulip user.

**Residual risk:** User names and emails are visible to the LLM. This is by design for the `resolve_user` fuzzy matching feature.

## Controls Summary

Our deployment uses these layered controls:

```
Layer 1: Channel Filter      — JD taxonomy, excludes sensitive channels
Layer 2: DM Exclusion         — No direct messages to LLM
Layer 3: Private Exclusion    — No private channels to LLM
Layer 4: Read-Only Mode       — No write tools registered
Layer 5: Agent Disable        — No autonomous tools, no background services
Layer 6: Audit Logging        — Structured trail of all access (no content)
Layer 7: Fail-Closed IDs      — Unknown stream IDs denied
Layer 8: Startup Notice       — Operator sees active config on stderr
```

## References

- [Anthropic data retention policy](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data) — 30-day retention for safety review
- [Anthropic commercial customer privacy](https://privacy.claude.com/en/collections/10663361-commercial-customers)
- [MCP security considerations](https://block.github.io/goose/blog/2025/03/26/mcp-security/)
- [Upstream repository](https://github.com/akougkas/zulipchat-mcp)
- [Fork repository](https://github.com/unfoldingWord/uw-zulip-mcp)
