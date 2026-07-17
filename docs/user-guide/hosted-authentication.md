# Hosted Mode & Authentication

Hosted mode turns one shared uw-zulip-mcp deployment into a multi-user
service **without storing any user credential server-side**. It implements
two independent authentication hops:

| Hop | Mechanism | What it answers |
|-----|-----------|-----------------|
| User → MCP server | OAuth 2.1 (FastMCP auth provider) | "May you talk to this server at all?" |
| MCP server → Zulip | Per-request user credentials via headers | "What may you see and do in Zulip?" |

## Threat model (what lives where)

- **User Zulip API keys: nowhere on the server.** Supplied by the client on
  every request via headers, held in a request-scoped context variable,
  used to call Zulip, then dropped. Never written to disk, database, or
  logs. A compromise of the server's disk and environment yields **zero
  user keys**.
- **Org bot key: server-side env/zuliprc**, same as today. One rotatable
  identity used by the agent control plane and message listener.
- **User keys at rest: on each user's own machine** (in their MCP client
  config), same trust model as a local `~/.zuliprc`.
- **Zulip site: pinned server-side** (`ZULIP_SITE`). Clients cannot point
  the server at another host, which closes the SSRF/key-exfiltration hole
  a client-supplied site would open.

Per-user permissions come for free: every Zulip call runs with the
requesting user's own key, so Zulip's native permission model (private
streams, DMs, roles) applies — on top of the fork's channel filter, which
still applies globally.

## Server setup

```bash
ZULIP_SITE=https://your-org.zulipchat.com \
ZULIPCHAT_HOSTED=1 \
zulipchat-mcp --transport http --host 0.0.0.0 --port 3000
```

or use the `--hosted` flag. Hosted mode requires a network transport and
refuses to start on stdio. Optionally add the org bot (`ZULIP_BOT_EMAIL`,
`ZULIP_BOT_API_KEY`) for agent-plane features.

In hosted mode:

- Tool calls without `X-Zulip-Email` / `X-Zulip-Key` headers fail with a
  clear error. There is no server-side user fallback.
- `switch_identity` is disabled (identity is per-request, not global).
- Startup cache warmup is skipped; caches fill per identity on demand and
  are **scoped per user** so one user's stream/user lists are never served
  to another.
- Audit events (when `ZULIPCHAT_AUDIT_ENABLED=true`) are stamped with the
  requesting user's email — never the key.

## OAuth 2.1 for the user → server hop

Configured entirely via environment (`ZULIPCHAT_AUTH_MODE`):

| Mode | Use case | Required env |
|------|----------|--------------|
| `none` (default) | Local use, or auth handled by a fronting proxy | — |
| `google` | Google Workspace orgs (recommended for unfoldingWord) | `ZULIPCHAT_AUTH_CLIENT_ID`, `ZULIPCHAT_AUTH_CLIENT_SECRET`, `ZULIPCHAT_AUTH_BASE_URL` |
| `oidc` | Any OIDC identity provider | `ZULIPCHAT_AUTH_CONFIG_URL`, client id/secret, `ZULIPCHAT_AUTH_BASE_URL` |
| `jwt` | Bearer JWTs minted by an external IdP/gateway | `ZULIPCHAT_AUTH_JWKS_URI`, `ZULIPCHAT_AUTH_ISSUER`, optional `ZULIPCHAT_AUTH_AUDIENCE` |
| `static` | Development/testing only | `ZULIPCHAT_AUTH_STATIC_TOKENS` |

`ZULIPCHAT_AUTH_BASE_URL` is the public URL of the MCP server itself
(the OAuth callback is registered under it).

Optional: `ZULIPCHAT_REQUIRE_EMAIL_MATCH=1` rejects calls where the OAuth
identity's email claim does not match `X-Zulip-Email` — a user cannot pair
their own OAuth session with someone else's leaked Zulip key unnoticed.

## Client setup (Claude Code)

Each user finds their API key in Zulip under **Personal settings →
Account & privacy → API key**, then:

```bash
claude mcp add --transport http zulipchat https://mcp.your-org.example/mcp \
  --header "X-Zulip-Email: you@your-org.org" \
  --header "X-Zulip-Key: YOUR_ZULIP_API_KEY"
```

When OAuth is enabled, Claude Code runs the browser flow automatically on
first connect; the Zulip headers ride along on every request afterwards.

**Key rotation / revocation:** invalidate the key in Zulip (same settings
page), then update the header in your client config. Nothing to clean up
server-side — the server never had it.

## Deployment requirements

- **TLS is mandatory.** Credentials travel in headers; terminate HTTPS at
  the proxy or use end-to-end TLS.
- **Do not log request headers** at the reverse proxy. Default `nginx`/
  `caddy` access logs don't; custom log formats must exclude `X-Zulip-*`.
- Rate-limit per client at the proxy if the server is internet-facing.

## What this deliberately does not do

- No per-user keys at rest, encrypted or otherwise (that was Option 3 —
  the honeypot).
- No OAuth to Zulip itself — Zulip has no OAuth provider. If that ever
  ships upstream, the second hop can be swapped without changing the
  first.
