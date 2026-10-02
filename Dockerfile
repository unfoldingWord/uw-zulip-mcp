# =====================================================================
# 1. Build Stage
# =====================================================================
# Wolfi (the hardened, minimal-CVE distro behind Chainguard Images) is
# used instead of python:*-slim (Debian, large attack surface).
#
# Python is pinned to 3.13: the locked pydantic-core (a PyO3/Rust
# extension) ships no cp314 wheel, so Chainguard's rolling `python:latest`
# (currently 3.14) forces a broken source build. 3.13 has prebuilt wheels
# for every dependency, so the frozen lockfile installs cleanly.
FROM cgr.dev/chainguard/wolfi-base:latest AS build

RUN apk add --no-cache python-3.13 py3.13-pip uv

WORKDIR /app

# Pre-compile bytecode for faster startup, copy (don't hardlink) into the
# venv so it survives the cross-stage COPY, and pin uv to the system 3.13.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON=python3.13 \
    UV_PYTHON_DOWNLOADS=never

COPY . /app

# Install all groups (dev tools needed for the test gate below).
RUN uv sync --frozen --all-groups

# Gate the build on the test suite before producing the production image.
# No pipe to `tail` here: the pipeline's exit status must be pytest's so a
# failing test actually fails the build.
RUN uv run pytest tests/ -q --tb=short

# Prune dev dependencies so only runtime packages ship in the venv.
RUN uv sync --frozen --no-dev


# =====================================================================
# 2. Production Stage
# =====================================================================
# Runtime image: Wolfi with the Python 3.13 runtime only — no pip, uv, or
# build toolchain — matching the interpreter path the venv was built against.
FROM cgr.dev/chainguard/wolfi-base:latest AS prod

RUN apk add --no-cache python-3.13

# Create the working directory owned by the non-root user so the server can
# write its project-local state (e.g. the .mcp/ DuckDB dir) at runtime.
RUN install -d -o 65532 -g 65532 /app
WORKDIR /app

# Copy the pruned application and virtual environment, owned by the built-in
# non-root account (uid/gid 65532 — wolfi-base's "nonroot", the conventional
# distroless/Chainguard id, so ownership is fixed and deterministic).
COPY --from=build --chown=65532:65532 /app /app

# Add the virtual environment's bin folder to PATH so the console script
# runs directly, without needing `uv run`.
ENV PATH="/app/.venv/bin:$PATH"

# Numeric id keeps the runtime user deterministic regardless of name mapping.
USER 65532:65532

# Reset the entrypoint (wolfi-base has none, but be explicit).
ENTRYPOINT []

# Expose the default MCP HTTP port
EXPOSE 3000

# Run the MCP server in streamable-HTTP mode, bound to all interfaces
CMD [ "zulipchat-mcp", "--read-only", "--disable-agents", "--transport", "http", "--host", "0.0.0.0" ]
