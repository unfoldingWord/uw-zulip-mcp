# Hosted Mode & Authentication (OAuth2-only)

Hosted mode turns one shared uw-zulip-mcp deployment into a multi-user service.
Clients authenticate with **OAuth2 only**; the server resolves each user's Zulip
API key from an **OpenBao/Vault** secret store and uses it to act in Zulip as
that user. It implements two authentication hops:

| Hop | Mechanism | What it answers |
|-----|-----------|-----------------|
| User → MCP server | OAuth 2.1 (FastMCP auth provider) | "Who are you?" |
| MCP server → Zulip | The user's Zulip API key, fetched from the vault | "What may you see and do in Zulip?" |

The user never sends a Zulip API key with requests. On first contact a user is
sent to a web page to add their key once; from then on the server fetches it
from the vault (cached in memory) automatically.

## How it works

1. The MCP client completes the OAuth login. Every request carries the OAuth
   token; the server reads the user's email from the validated token.
2. On a tool call, the server looks up the user's Zulip API key:
   in-memory cache first, then the vault.
3. **First contact (no key stored):** the tool call returns a short-lived,
   signed `/enroll` link. The user opens it, follows the instructions to copy
   their Zulip API key, and submits it. The server validates the key against
   Zulip, confirms the key belongs to the same email, then stores it in the
   vault and caches it.
4. Subsequent calls run as that user with no further prompts.
5. Cached keys expire after a day of inactivity (sliding TTL) and are re-fetched
   from the vault on demand.

## Threat model (what lives where)

- **User Zulip API keys: encrypted in OpenBao/Vault**, fetched on demand and
  cached in memory only. Never written to the server's disk or logs.
- **The server holds vault credentials** (AppRole) that can read user keys on
  demand. Treat the server and its vault policy as sensitive: use a
  least-privilege policy, short cache TTLs, and audit logging. A live server
  compromise can expose keys — this is the accepted trade-off of OAuth2-only.
- **Identity binding:** a submitted key is stored only if Zulip confirms it and
  its Zulip email matches the OAuth email, so a user cannot bind someone else's
  account.
- **Zulip site: pinned server-side** (`ZULIP_SITE`). Clients cannot point the
  server at another host.
- **Org bot key: server-side env/zuliprc**, unchanged, for the agent control
  plane and message listener.

Per-user permissions come for free: every Zulip call runs with the requesting
user's own key, so Zulip's native permission model applies (on top of the
fork's channel filter, which still applies globally).

## Server setup

```bash
ZULIP_SITE=https://your-org.zulipchat.com \
ZULIPCHAT_HOSTED=1 \
ZULIPCHAT_AUTH_MODE=google \
ZULIPCHAT_AUTH_CLIENT_ID=... ZULIPCHAT_AUTH_CLIENT_SECRET=... \
ZULIPCHAT_AUTH_BASE_URL=https://mcp.your-org.example \
ZULIPCHAT_PUBLIC_URL=https://mcp.your-org.example \
ZULIPCHAT_ENROLL_SECRET=$(openssl rand -hex 32) \
OPENBAO_ADDR=https://bao.your-org.example \
OPENBAO_ROLE_ID=... OPENBAO_SECRET_ID=... \
zulipchat-mcp --hosted --transport http --host 0.0.0.0 --port 3000
```

Hosted mode requires a network transport and refuses to start on stdio.

## OAuth 2.1 for the user → server hop

Configured via `ZULIPCHAT_AUTH_MODE`:

| Mode | Use case | Required env |
|------|----------|--------------|
| `google` | Google Workspace orgs (recommended for unfoldingWord) | `ZULIPCHAT_AUTH_CLIENT_ID`, `ZULIPCHAT_AUTH_CLIENT_SECRET`, `ZULIPCHAT_AUTH_BASE_URL` |
| `oidc` | Any OIDC identity provider | `ZULIPCHAT_AUTH_CONFIG_URL`, client id/secret, `ZULIPCHAT_AUTH_BASE_URL` |
| `jwt` | Bearer JWTs minted by an external IdP/gateway | `ZULIPCHAT_AUTH_JWKS_URI`, `ZULIPCHAT_AUTH_ISSUER`, optional `ZULIPCHAT_AUTH_AUDIENCE` |
| `static` | Development/testing only | `ZULIPCHAT_AUTH_STATIC_TOKENS` |

An auth provider is required in OAuth2-only mode — it is how the server learns
the user's email.

**The email scope is required.** The server keys each user by the `email` claim
in their OAuth token. For `google` and `oidc`, scopes default to
`openid email profile`; override with `ZULIPCHAT_AUTH_SCOPES` if needed. If the
token has no email claim, tool calls fail with "no authenticated identity" and
the server logs the claims it did receive. For `jwt` mode, ensure your IdP puts
`email` in the JWT.

## OpenBao / Vault

| Variable | Default | Purpose |
|----------|---------|---------|
| `OPENBAO_ADDR` | `http://127.0.0.1:8200` | Vault address |
| `OPENBAO_ROLE_ID` / `OPENBAO_SECRET_ID` | — | AppRole login (recommended) |
| `OPENBAO_TOKEN` | — | Direct token (dev/testing; bypasses AppRole) |
| `OPENBAO_KV_MOUNT` | `secret` | KV v2 mount |
| `OPENBAO_KV_PATH` | `zulip-mcp/users` | Base path for user secrets |
| `OPENBAO_NAMESPACE` | — | Optional namespace |
| `OPENBAO_TLS_VERIFY` | `1` | Set `0` to disable TLS verification (dev only) |
| `OPENBAO_CACERT` | — | Path (inside the container) to a PEM CA bundle, for a private/internal CA |

Each user's key is stored at `<mount>/data/<path>/<sha256(email)>`. The hash
keeps the path clean and avoids listing everyone's email; operators can still
map an email to its path by hashing the address the same way.

The AppRole policy only needs create/read/update on that path prefix.

### Private / internal CA

If OpenBao presents a certificate signed by your own CA, the server must trust
that CA or TLS verification fails with
`CERTIFICATE_VERIFY_FAILED ... unable to get local issuer certificate`. Do not
disable verification. Instead, give the server the CA bundle and mount it into
the container, then point `OPENBAO_CACERT` at it.

Docker run:

```bash
docker run ... \
  -v /host/path/your-ca.pem:/etc/zulip-mcp/openbao-ca.pem:ro \
  -e OPENBAO_CACERT=/etc/zulip-mcp/openbao-ca.pem \
  ...
```

docker-compose:

```yaml
services:
  zulip-mcp:
    environment:
      OPENBAO_CACERT: /etc/zulip-mcp/openbao-ca.pem
    volumes:
      - ./your-ca.pem:/etc/zulip-mcp/openbao-ca.pem:ro
```

Notes:
- The PEM must contain the **root CA and any intermediate CAs**. Do not include
  OpenBao's own leaf certificate — OpenBao presents that during the TLS
  handshake.
- This file is the **sole trust anchor** for the OpenBao connection: it
  replaces the default/public CA store, it is not added to it. To trust a
  private CA and public CAs on the same connection, concatenate your CA with
  the public bundle into one PEM and point `OPENBAO_CACERT` at it.
- Mount it read-only; it must be readable by the container's non-root user
  (a CA certificate is public, so world-readable is fine).
- Only the OpenBao client uses this CA. Zulip validation still uses the default
  public trust store, so a Zulip Cloud site keeps working unchanged.


## Enrollment and cool-off

| Variable | Default | Purpose |
|----------|---------|---------|
| `ZULIPCHAT_ENROLL_SECRET` | random per-process | HMAC secret for enrollment links. Set this in production so links survive restarts and work across replicas. |
| `ZULIPCHAT_PUBLIC_URL` | `ZULIPCHAT_AUTH_BASE_URL` | Public URL used to build enrollment links |
| `ZULIPCHAT_ENROLL_TOKEN_TTL_SECONDS` | `900` | Enrollment link lifetime |
| `ZULIPCHAT_ENROLL_MAX_ATTEMPTS` | `6` | Failed submissions before a cool-off |
| `ZULIPCHAT_ENROLL_COOLOFF_SECONDS` | `900` | Cool-off duration after too many failures |
| `ZULIPCHAT_KEY_CACHE_TTL_SECONDS` | `86400` | In-memory key cache inactivity TTL |

## Client setup (Claude Code)

```bash
claude mcp add --transport http zulipchat https://mcp.your-org.example/mcp
```

Claude Code runs the OAuth browser flow on first connect. The first time you run
a Zulip tool, you receive an `/enroll` link; open it, paste your Zulip API key
(from **Personal settings → Account & privacy → API key** in Zulip), and submit.
After that, everything works automatically.

**Key rotation / revocation:** rotate the key in Zulip, then run any Zulip tool
again and use the fresh `/enroll` link to submit the new key. An operator can
also delete a user's stored key from the vault.

## Deployment requirements

- **TLS is mandatory.** The enrollment page and OAuth tokens must travel over
  HTTPS. Terminate TLS at the proxy or use end-to-end TLS.
- **Do not log request bodies or the enrollment form** at the reverse proxy.
- **Single vs multiple replicas:** the key cache and the cool-off counters are
  in-memory per replica. That is fine for the cache (a cold replica simply
  re-fetches from the vault). If you run more than one replica, move the
  cool-off counters to a shared store so the limit holds across replicas.
- Set `ZULIPCHAT_ENROLL_SECRET` explicitly so enrollment links are valid across
  restarts and replicas.

## What this deliberately does not do

- No OAuth token is forwarded to Zulip — Zulip's API has no OAuth. The server
  exchanges the OAuth identity for the user's stored API key instead.
- No per-user keys are kept on the server's disk; they live in the vault and a
  short-lived in-memory cache.
