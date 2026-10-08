# Release Runbook

This is the release process for uw-zulip-mcp. The shipped artifact is a **Docker
image** on Docker Hub (`unfoldingword/zulipchat-mcp`); this fork does not publish
to PyPI. Follow the steps in order. If a gate fails, fix the root cause and rerun
the failed command plus the gate that contains it.

## Stages and images

| Stage | Branch / trigger | Image tags |
|-------|------------------|-----------|
| Develop (rolling) | push to `develop` | `latest`, `develop-<sha>` |
| Production (release) | tag `vX.Y.Z` on `main` | `X.Y.Z`, `stable` |

Pushes to `main` do not build an image; only release tags do.

`develop` auto-publishes `latest` on every push. **A production/`stable` image is
cut only by tagging a release** — that is what "release" means here.

## Release standard

- A release is not ready until the source tree and the MCP stdio server pass from
  a clean environment, and the Docker image builds (its Dockerfile runs the test
  suite as a build gate).
- Startup smoke tests use fake credentials and must not contact a real Zulip
  server. Real Zulip testing is reserved for targeted manual checks.
- Framework feature changes are release-risk changes. If a FastMCP constructor
  argument, tool-registration option, optional dependency extra, background task,
  lifespan hook, or async/sync boundary changes, add or update a contract test and
  run the MCP stdio smoke.

## One-time prerequisites

- [ ] Docker Hub credentials set as repo secrets: `DOCKER_BUILD_USERNAME`,
      `DOCKER_BUILD_TOKEN` (push access to `unfoldingword/zulipchat-mcp`).
- [ ] Branch protection requires CI before merge to `main`.
- [ ] Tag and release permissions are limited to maintainers.

## Failure modes to check explicitly

These checks exist because v0.7.0 failed at startup even though simple entrypoint
checks passed.

- Package extras match enabled framework features (e.g. FastMCP task support
  requires `fastmcp[...,tasks]`).
- Tool registration is tested with a real `FastMCP`, not only mocks.
- Server startup is tested through MCP stdio with fake credentials, including
  `ping`, `list_tools`, and `server_info`.
- Background-task tools are async-safe and only long-running tools opt in.
- Background services start/stop through the FastMCP lifespan, not at import time.

## Release steps

### 1. Decide the version number (semver)
- `PATCH` for bug fixes and docs-only releases.
- `MINOR` for new tools/features or non-breaking changes.
- `MAJOR` for breaking API or configuration changes.

### 2. Promote develop to main
Releases are tagged on `main`. Merge the release-ready `develop` into `main`
first (PR or fast-forward), so the tag sits on the production branch.

### 3. Start from a clean environment
```bash
git status --short
rm -rf .venv .pytest_cache **/__pycache__ htmlcov .coverage* coverage.xml .uv_cache
uv sync --reinstall
```

### 4. Bump version strings
```bash
uv run python scripts/bump_version.py --dry-run X.Y.Z
uv run python scripts/bump_version.py X.Y.Z
```
This updates the scripted version locations (`pyproject.toml`,
`src/zulipchat_mcp/__init__.py`, `src/zulipchat_mcp/tools/system.py`,
`server.json`, `AGENTS.md`, `ROADMAP.md`). Audit Markdown for stale version
references that are intentionally not scripted.

### 5. Update release notes
- `CHANGELOG.md`: new top section with date and user-visible changes. This is the
  source of truth; the GitHub release body can be generated from it.
- Any user/integration docs affected by behavior, run commands, or tool counts.

### 6. Source quality gates
```bash
uv sync
uv run pytest -q
uv run mypy src
uv run ruff check .
uv run ruff format --check .
```
The full pytest run is the gate (it enforces the 60% coverage floor). Use
`--no-cov` only for exploratory subsets, never as release evidence.

### 7. Preflight and startup smoke
```bash
uv run python scripts/release_preflight.py --version X.Y.Z --allow-dirty
uv run python scripts/mcp_stdio_smoke.py --expected-version X.Y.Z -- uv run zulipchat-mcp
```
Optional packaging sanity (builds a wheel and runs the installed-wheel stdio
smoke — catches missing extras and startup-only failures):
```bash
uv build
scripts/pre_release_smoke.sh --version X.Y.Z --allow-dirty
```

### 8. Commit on main
Do not stage generated artifacts (`dist/`, `htmlcov/`, `.coverage*`,
`coverage.xml`).
```bash
git add AGENTS.md CHANGELOG.md ROADMAP.md pyproject.toml \
  server.json uv.lock src/zulipchat_mcp tests scripts .github docs README.md \
  CONTRIBUTING.md RELEASING.md
git commit -m "chore: release X.Y.Z"
```
(`CLAUDE.md` is a pointer to `AGENTS.md`; no need to stage it for version bumps.)

### 9. Post-commit preflight
```bash
uv run python scripts/release_preflight.py --version X.Y.Z
```
This must pass without `--allow-dirty`.

### 10. Tag and push — this publishes the image
```bash
git push
git tag vX.Y.Z
git push --tags
```
Pushing the `vX.Y.Z` tag triggers `.github/workflows/docker-build-push.yaml`,
which builds and pushes `X.Y.Z` and `stable` to Docker Hub.

Optional GitHub release notes:
```bash
gh release create vX.Y.Z --title "vX.Y.Z - Short Description" --generate-notes
```

### 11. Verify the published image
- [ ] The Docker workflow run succeeded (Actions tab).
- [ ] Docker Hub shows the new `X.Y.Z` and updated `stable` tags.
- [ ] A pull reports the new version:
```bash
docker run --rm unfoldingword/zulipchat-mcp:X.Y.Z zulipchat-mcp --version
```

### 12. Notify community
- Comment on fixed issues and addressed PRs with the released version.
- Credit reporters and contributors.

## Troubleshooting

**Preflight failed** — fix version alignment or missing changelog section; rerun
with `--allow-dirty` until clean, then without.

**MCP stdio smoke failed** — release blocker. Inspect whether startup fails during
configuration, FastMCP construction, tool registration, lifespan startup, or
`server_info`. Common causes: missing dependency extras, sync functions registered
as background tasks, bad type annotations, stdout pollution, import-time side
effects.

**Docker build/push failed** — check the Actions logs. If the tag is wrong, delete
the remote tag (`git push --delete origin vX.Y.Z`), fix the release commit, retag,
and push again. Verify the `DOCKER_BUILD_USERNAME` / `DOCKER_BUILD_TOKEN` secrets
are present and valid.
