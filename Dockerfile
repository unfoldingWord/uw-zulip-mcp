# =====================================================================
# 1. Build Stage
# =====================================================================
FROM python:3.13-slim AS build

# Set up the working directory
WORKDIR /app

# Optional: Instructs uv to pre-compile executable bytecode for faster startup
ENV UV_COMPILE_BYTECODE=1

# FIX: Copy files
COPY . /app

# Install uv
RUN pip install uv

# Install dependencies
RUN uv sync --all-groups 2>&1

# Run tests to gate the build before creating the production image
RUN uv run pytest tests/ -q --tb=line 2>&1 | tail -n 3


# =====================================================================
# 2. Production Stage
# =====================================================================
FROM python:3.13-slim AS prod

WORKDIR /app

# Copy the synchronized application and virtual environment from the build stage
COPY --from=build /app /app

# Add the virtual environment's bin folder to the system PATH.
# This eliminates the need to use 'uv run' in production entirely!
ENV PATH="/app/.venv/bin:$PATH"

# Reset the entrypoint (Chainguard defaults this to /usr/bin/python)
ENTRYPOINT []

# Expose the default MCP HTTP port
EXPOSE 3000

# Run the MCP server in streamable-HTTP mode, bound to all interfaces
CMD [ "zulipchat-mcp", "--read-only", "--disable-agents", "--transport", "http", "--host", "0.0.0.0" ]
