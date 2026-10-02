# Roadmap

## v0.8.0 (Current)

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
