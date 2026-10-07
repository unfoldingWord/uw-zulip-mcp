"""Shared MCP tool registration helpers."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.tasks import TaskConfig


def optional_background_task(poll_seconds: int = 5) -> TaskConfig:
    """Return explicit optional MCP background-task support metadata."""
    return TaskConfig(mode="optional", poll_interval=timedelta(seconds=poll_seconds))


def register_tool(
    mcp: FastMCP[Any],
    fn: Callable[..., Any],
    *,
    name: str,
    description: str,
    task: TaskConfig | None = None,
) -> None:
    """Register a tool with explicit task semantics.

    FastMCP server-wide task defaults are intentionally disabled in server.py.
    Long-running tools opt in here so sync and fast tools are not accidentally
    advertised as background-task capable.
    """
    kwargs: dict[str, Any] = {"name": name, "description": description}
    if task is not None:
        kwargs["task"] = task
    mcp.tool(**kwargs)(fn)


async def _ensure_required_arrays_async(mcp: FastMCP[Any]) -> None:
    for tool in await mcp.list_tools():
        params = tool.parameters
        if (
            isinstance(params, dict)
            and params.get("properties")
            and "required" not in params
        ):
            params["required"] = []


def normalize_tool_schemas(mcp: FastMCP[Any]) -> None:
    """Add an explicit empty ``required`` array to all-optional tool schemas.

    FastMCP omits ``required`` when a tool has parameters but none are required.
    JSON Schema treats that as identical to ``required: []``, but some MCP
    clients and linters flag the omission, so we add it explicitly. Tools that
    already have required parameters are left untouched. Call once after all
    tools are registered.
    """
    asyncio.run(_ensure_required_arrays_async(mcp))
