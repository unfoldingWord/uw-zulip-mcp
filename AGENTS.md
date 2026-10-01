# Repository Guidelines

Single source of truth for working in this repository. `CLAUDE.md` is a link to
this file, so guidance stays in one place for every assistant and contributor.

## Current Status (v0.7.1)

**Distribution**: Docker image `unfoldingword/zulipchat-mcp` on Docker Hub (`latest` = develop, `stable` = latest release). Local/dev run from source: `uvx --from git+https://github.com/akougkas/zulipchat-mcp.git zulipchat-mcp`. This fork does not publish to PyPI.

ZulipChat MCP is a Model Context Protocol (MCP) server that connects AI
assistants to Zulip. It uses the FastMCP framework with DuckDB for persistence
and an async-first architecture.

## Project Structure & Module Organization
- Source code lives in `src/zulipchat_mcp/`:
  - `tools/` (tool groups), `core/` (client, cache, commands, identity), `services/` (listener, scheduler), `integrations/` (client installers), `utils/` (logging, metrics, db), `config.py` (configuration), `server.py` (entry point and CLI).
- Tests are in `tests/` (pytest with `slow` and `integration` markers).
- Config via CLI flags or environment; copy `.env.example` to `.env` for local dev. Entry points: `zulipchat-mcp`, `zulipchat-mcp-integrate`.

### Dual identity
The client (`core/client.py`) supports both user and bot credentials:
- User identity for reading/search operations.
- Bot identity for posting messages and administrative tasks.
- Switch via the `switch_identity` tool.

### Imports
Production code under `src/zulipchat_mcp/` uses package-relative imports:
```python
from .core.client import ZulipClientWrapper
from .tools.messaging import register_messaging_tools
```
Tests use `from src.zulipchat_mcp.*` because pytest runs with the repo root on `sys.path`. Never write `from src.zulipchat_mcp.*` inside `src/`.

## Build, Test, and Development Commands
- `uv sync` — install dependencies. Never use pip; add packages with `uv add <package>`.
- `uv run zulipchat-mcp --zulip-config-file ~/.zuliprc [--enable-listener]` — run the server locally.
- `uvx zulipchat-mcp` — quick run via the uvx shim.
- `uv run pytest -q` — run tests. Use `-m "not slow and not integration"` to skip long tests; `--cov=src` for coverage. Gate is 60%.
- `uv run ruff format` — format; `uv run ruff check .` — lint; `uv run mypy src` — type-check.
- Optional security checks: `uv run bandit -q -r src` and `uv run safety check`.
- Quick connection check:
  ```bash
  uv run python -c "from zulipchat_mcp.config import ConfigManager; from zulipchat_mcp.core.client import ZulipClientWrapper; c = ZulipClientWrapper(ConfigManager()); print('Connected:', c.identity_name)"
  ```
- Import validation: `uv run python -c "from zulipchat_mcp.server import main; print('OK')"`

## Coding Style & Naming Conventions
- Python 3.10+, 4-space indent, line length 88. Ruff handles both formatting (`ruff format`) and linting (`ruff check`: pycodestyle, pyflakes, isort, bugbear, pyupgrade). Keep imports sorted.
- Names: functions/variables `snake_case`, classes `CamelCase`, constants `UPPER_SNAKE_CASE`, modules `lower_snake_case.py`.
- Type hints required for public APIs; prefer async/await for I/O.
- **Less is more.** Elegant simplicity is the primary metric: every line must justify its existence, prefer Zulip's native capabilities over custom code, remove complexity rather than manage it, and minimize abstractions.
- File operations: prefer editing existing files over creating new ones, consider deletion before addition, read a file before modifying it, and match existing patterns.

## Tool Registration & Modes
Register tools through `tools/registration.py`, not bare `@mcp.tool`:
```python
from .registration import register_tool, optional_background_task

register_tool(
    mcp,
    my_tool_fn,
    name="my_tool",
    description="One-line, action-oriented.",
    task=optional_background_task(),  # only for long-running tools
)
```
Server-wide task advertisement is intentionally disabled in `server.py` (commit `70d3779`). Pass `task=optional_background_task()` only for genuinely long-running tools (`teleport_chat`, `wait_for_response`, `listen_events`); normal fast tools omit `task=`. Each tool group exposes `register_*_tools(mcp)`.

Tool modes:
- **Default**: 20 core tools via `register_core_tools(mcp)` (9 in read-only).
- **Extended (56 tools total)**: `--extended-tools` flag or `ZULIPCHAT_EXTENDED_TOOLS=true` also calls `register_extended_tools(mcp)`. The split keeps token overhead low for the common case.

## Testing Guidelines
- Place tests under `tests/` as `test_*.py`; classes `Test*`, functions `test_*`.
- Mark long/external tests `@pytest.mark.slow` or `@pytest.mark.integration` and gate them in CI via markers.
- Prefer fast, deterministic unit tests; mock Zulip API calls so tests are network-free. Maintain the 60% coverage gate with targeted tests that do not alter functionality.
- Always use `uv` (no direct Python). Before major coverage pushes, clean caches: `rm -rf .venv .pytest_cache **/__pycache__ htmlcov .coverage* coverage.xml .uv_cache && uv sync --reinstall`.
- Contract-only runs (`-k "contract_"`) trip the global coverage gate; use the full suite, or append `--no-cov` when exploring locally.

## MCP Sampling & LLM Analytics (v0.4+)

### Context parameter (required, not optional)
LLM-powered tools require the FastMCP-injected `Context`. Do not make it optional.
```python
async def analyze_stream_with_llm(stream_name: str, ctx: Context) -> dict:
    result = await ctx.sample(f"Analyze stream {stream_name}")
```
`ctx: Context | None = None` with a null guard defeats sampling. The client controls model selection and permissions. If you see "Client does not support sampling", ensure `ctx` is required (no `| None`), remove null guards, and confirm the client (Claude Code, Gemini) has sampling enabled.

### Bidirectional agent communication (v0.4+)
Agent-to-user pipeline in `src/zulipchat_mcp/tools/agents.py`:
- `register_agent()`, `ensure_agent_session()`, `agent_message()`, `request_user_input()`, `wait_for_response()`, `poll_agent_events()`.
- A background MessageListener processes Zulip replies; `zulipchat-mcp-hook` bridges Claude Code hook events into the same session model.

### Emoji registry (v0.4+)
`core/emoji_registry.py` enforces 12 approved emoji for agent reactions: `thumbs_up`, `heart`, `rocket`, `fire`, `tada`, `check_mark`, `warning`, `thinking`, `bulb`, `wrench`, `star`, `zap`. Others are rejected at runtime; validate with `validate_emoji_for_agent()`.

### Command chains (execute_chain)
Workflow automation with context passed between operations:
```python
execute_chain(
    [
        {"type": "search_messages", "params": {"query_key": "search_query"}},
        {
            "type": "conditional_action",
            "params": {
                "condition": "len(context['search_results']) > 0",
                "true_action": {"type": "send_message", "params": {...}},
            },
        },
    ]
)
```

## Project Skills (`.claude/skills/`)
Three project skills extend the Zulip control plane. They activate when a Claude
Code session is bound to a Zulip topic via `zulipchat-mcp-hook` and read
`ZULIPCHAT_SESSION_ID`, `ZULIPCHAT_SESSION_STREAM`, `ZULIPCHAT_SESSION_TOPIC`:
- **`zulipchat-session-operator`** — treats Zulip as the owner control plane; polls `poll_agent_events`, handles `/status`, `/pause`, `/resume`, `/cancel`, `/handoff`; lifecycle-only posting.
- **`zulipchat-loop`** — per-cycle policy for `/loop`: poll events, apply steering, emit at most one lifecycle message, do one unit of work.
- **`zulipchat-notifyme`** — explicit post into the bound topic with a category (`message`/`started`/`blocked`/`waiting`/`completed`/`failed`).

If a session is not bound, these skills stop and explain rather than calling MCP tools blind.

## Commit & Pull Request Guidelines
- Use Conventional Commits: `feat:`, `fix:`, `docs:`, `chore:`, `release:` (see `git log`).
- PRs should include: clear summary/motivation, linked issues, tests (or rationale), and example CLI invocation/output when relevant.
- Keep changes minimal and focused; update `README.md`/`AGENTS.md` when behavior or commands change.
- Community PRs are labeled `community`. Prefer merging over reimplementing.

## Distribution & Installation Testing
- **Primary artifact**: the Docker image `unfoldingword/zulipchat-mcp` on Docker Hub. `latest` tracks `develop`; `stable` and `X.Y.Z` are cut by release tags (see Release Process).
- **Run from source (local/dev)**: `uvx --from git+https://github.com/akougkas/zulipchat-mcp.git zulipchat-mcp`.
- **Credential loading**: zuliprc files or env vars; config-file env vars (`ZULIP_CONFIG_FILE`, `ZULIP_BOT_CONFIG_FILE`) are checked before CLI flags.
- **Claude Code integration** (local stdio): use the `--` separator (env vars before `--`):
  ```bash
  claude mcp add zulipchat -e ZULIP_EMAIL=bot@org.com -e ZULIP_API_KEY=key -e ZULIP_SITE=https://org.zulipchat.com -- uvx --from git+https://github.com/akougkas/zulipchat-mcp.git zulipchat-mcp
  ```
- **Before release**: run the fake-credential MCP stdio smoke. The Docker build also runs the full test suite as a build gate.

## Security & Configuration Tips
- Do not commit secrets. Use `.env` (gitignored). Common vars: `ZULIP_EMAIL`, `ZULIP_API_KEY`, `ZULIP_SITE` (plus optional `ZULIP_BOT_EMAIL`, `ZULIP_BOT_API_KEY`).
- Prefer CLI flags for credentials in MCP clients. Administrative/destructive tools are not exposed to AI clients by default.
- Message listener startup is lazy; `--enable-listener` starts it eagerly for backward compatibility.
- Optional checks before release: `uv run bandit -q -r src` and `uv run safety check`.

## Common Issues
- **DuckDB lock after unclean shutdown**: stale-lock recovery shipped in commit `3db725a`. If you still hit "Database is locked by another process", ensure no zombie `zulipchat-mcp` process holds `.mcp/zulipchat/zulipchat.duckdb`.
- **Coverage / cache contamination**: clean caches (see Testing Guidelines) before major test runs.
- **LLM analytics "not supported"**: see the Context parameter note under MCP Sampling.

## Documentation Resources

### User Documentation
- [Installation Guide](docs/user-guide/installation.md) - Detailed setup instructions
- [Quick Start Tutorial](docs/user-guide/quick-start.md) - Get running quickly
- [Configuration Reference](docs/user-guide/configuration.md) - All configuration options
- [Troubleshooting](docs/TROUBLESHOOTING.md) - Common issues and solutions

### Developer Documentation
- [Architecture Overview](docs/developer-guide/architecture.md) - System design and components
- [Tool Categories](docs/developer-guide/tool-categories.md) - Tool organization patterns
- [Foundation Components](docs/developer-guide/foundation-components.md) - Core building blocks
- [Testing Guide](docs/testing/README.md) - Testing strategies and coverage requirements

### API Reference
- [Messaging Tools](docs/api-reference/messaging.md) - Message operations
- [Stream Tools](docs/api-reference/streams.md) - Stream management
- [Event Tools](docs/api-reference/events.md) - Real-time events
- [User Tools](docs/api-reference/users.md) - User management
- [Search Tools](docs/api-reference/search.md) - Search and analytics
- [File Tools](docs/api-reference/files.md) - File operations

### Release Documentation
- [Release Checklist](RELEASING.md) - Step-by-step release process
- [Full Documentation Index](docs/README.md)
- [Changelog](CHANGELOG.md)

## Release Process

Full runbook: [RELEASING.md](RELEASING.md). A release is a git tag `vX.Y.Z` on
`main`; the tag triggers the Docker workflow to publish `X.Y.Z` / `X.Y` / `stable`
to Docker Hub. `develop` publishes `latest` automatically. This fork does not
publish to PyPI.

```bash
uv run python scripts/bump_version.py X.Y.Z   # bump scripted version locations
# update CHANGELOG.md manually
uv sync
uv run pytest -q && uv run mypy src && uv run ruff check . && uv run ruff format --check .
uv run python scripts/release_preflight.py --version X.Y.Z --allow-dirty
uv run python scripts/mcp_stdio_smoke.py --expected-version X.Y.Z -- uv run zulipchat-mcp
git add AGENTS.md CHANGELOG.md ROADMAP.md pyproject.toml server.json uv.lock src/zulipchat_mcp tests scripts .github docs README.md CONTRIBUTING.md RELEASING.md
git commit -m "chore: release X.Y.Z"
uv run python scripts/release_preflight.py --version X.Y.Z
git tag vX.Y.Z && git push && git push --tags   # the tag triggers the Docker build
```

Release invariants:
- The tag must match `pyproject.toml` exactly (`vX.Y.Z` ↔ `version = "X.Y.Z"`).
- Versions stay in sync across `pyproject.toml`, `src/zulipchat_mcp/__init__.py`, `src/zulipchat_mcp/tools/system.py`, `server.json`, and release docs; `release_preflight.py` verifies this.
- `develop` → `latest` is automatic; `stable` and semver images come only from release tags.
- After releasing, verify the image on Docker Hub and with `docker run --rm unfoldingword/zulipchat-mcp:X.Y.Z zulipchat-mcp --version`.

## Open Source Community Practices

- **Respond to issues and PRs within 48 hours.** Even "Looking into this" is enough.
- **Label on triage**: `bug`, `enhancement`, `good first issue`, `help wanted`, `community`, `needs-triage`, `dependencies`, `fastmcp`, `mcp-tools`, `breaking-change`.
- **Prefer merging community PRs** over reimplementing the same fix. If already fixed independently, close with explicit credit.
- **After each release**, notify reporters on fixed issues with the version and upgrade instructions.
