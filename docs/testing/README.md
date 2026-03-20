# Testing Guide

## Standard commands

```bash
uv run pytest -q -m "not slow and not integration"   # 651 tests
uv run ruff check .                                   # Linting
uv run mypy src                                       # Type checking (55 source files)
uv run bandit -r src/zulipchat_mcp -ll -ii -q \
  -s B110,B112,B311,B324,B307,B608                    # Security scan
```

## Coverage gate

- Coverage threshold is `60%` (configured in `pyproject.toml`).
- Running a single test file will fail the coverage gate — use `--no-cov` for targeted runs.

## Fast local run

```bash
uv run pytest -q -m "not slow and not integration" --no-cov
```

## Test categories

| Category | Location | Count |
|----------|----------|-------|
| Channel filter | `tests/core/test_channel_filter.py` | 60 |
| Audit logging | `tests/core/test_audit.py` | 8 |
| Cache env config | `tests/core/test_cache_env.py` | 12 |
| Bot validation | `tests/test_bot_validation.py` | 5 |
| Tool tiers | `tests/tools/test_tool_tiers.py` | 36 |
| Upstream tests | `tests/` (various) | ~530 |

## Contract-only run note

Contract-only subsets can fail the global coverage gate. Use:

```bash
uv run pytest -q -k "contract_" --no-cov
```

## Clean rebuild

```bash
rm -rf .venv .pytest_cache **/__pycache__ htmlcov .coverage* coverage.xml .uv_cache
uv sync --reinstall
```
