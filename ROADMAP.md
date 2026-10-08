# Roadmap

## v0.9.0 (Current)

Released 2026-10-08 — Docker image `unfoldingword/zulipchat-mcp`

**Highlights:**
- Identity allowlist for hosted mode (fail-closed): `ZULIPCHAT_ALLOWED_EMAIL_DOMAINS` / `ZULIPCHAT_ALLOWED_EMAILS`. **Hosted deployments must now set an allowlist.**
- Enrollment hardening: single-use links, link expiry shown on the page, and automatic re-enrollment when Zulip rejects a rotated key
- Unified JSON logging — app and Uvicorn logs now share one structured format
- MCP tool usability: verified per-parameter descriptions and return shapes, explicit `required` arrays, and fixes to `get_users` and `get_streams` parameters

## v0.8.0

Released 2026-10-02 — Docker image `unfoldingword/zulipchat-mcp`

**Highlights:**
- OAuth2-only hosted mode with an OpenBao/Vault-backed per-user key store
- Docker deploy pipeline: `develop` → `latest`, release tags → `stable` + semver
- Hardened image (Wolfi base, non-root) and a full dependency refresh (FastMCP 3.4.7)
- Removed PyPI publishing; ships as a Docker image only

## Planned (Next)

### Feature 1: Multi-Organization Support
**Problem**: Users with multiple Zulip orgs (work, personal, open-source) can't switch contexts.

**Solution**:
- Named profiles in config: `--profile work` / `--profile personal`
- Profile registry: `~/.config/zulipchat-mcp/profiles.json`
- Runtime switching: `switch_organization` tool
- Auto-discovery of multiple zuliprc files

**Example**:
```bash
uvx zulipchat-mcp --profile work
uvx zulipchat-mcp --profile personal
```

### Feature 2: Plugin Marketplace Packaging
**Problem**: Different AI platforms have different extension formats.

**Target platforms**:
- MCP Registry (modelcontextprotocol.io)
- Anthropic Tool Library
- Google Gemini Extensions
- OpenAI GPT Actions
- VS Code / Cursor extensions

**Approach**:
- Adapter layer per platform (same core, different packaging)
- `plugins/` directory with platform-specific manifests
- Single `uv build --target=<platform>` command

---

## Next Session Agenda
1. List zulipchat-mcp in public MCP catalogs
2. Submit to Anthropic/Google extension directories
3. Create promotional materials (demo GIFs, etc.)
