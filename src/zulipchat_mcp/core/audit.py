"""Audit logging for MCP tool invocations.

Logs which tools were invoked, which channels were accessed, and what
searches were performed — but never logs message content. Designed for
organizational accountability and incident response.

Audit events are emitted via Python's standard logging at a configurable
level (default: INFO) to a dedicated "zulipchat_mcp.audit" logger. This
allows operators to route audit logs to a separate file or service via
standard logging configuration.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

# Dedicated audit logger — separate from application logs so operators
# can route it independently (e.g., to a file, syslog, or SIEM)
audit_logger = logging.getLogger("zulipchat_mcp.audit")

_AUDIT_ENABLED: bool = False


def init_audit_logging() -> None:
    """Initialize audit logging from environment configuration.

    Environment variables:
        ZULIPCHAT_AUDIT_ENABLED: "true" to enable (default: false)
        ZULIPCHAT_AUDIT_FILE: Path to audit log file (optional)
        ZULIPCHAT_AUDIT_LEVEL: Log level for audit events (default: INFO)
    """
    global _AUDIT_ENABLED

    enabled = os.getenv("ZULIPCHAT_AUDIT_ENABLED", "").lower()
    _AUDIT_ENABLED = enabled in ("true", "1", "yes", "on")

    if not _AUDIT_ENABLED:
        return

    level_str = os.getenv("ZULIPCHAT_AUDIT_LEVEL", "INFO").upper()
    level = getattr(logging, level_str, logging.INFO)
    audit_logger.setLevel(level)

    # Add file handler if configured
    audit_file = os.getenv("ZULIPCHAT_AUDIT_FILE")
    if audit_file:
        handler = logging.FileHandler(audit_file)
        handler.setFormatter(
            logging.Formatter(
                '{"timestamp": "%(asctime)s", "level": "%(levelname)s", %(message)s}'
            )
        )
        audit_logger.addHandler(handler)

    # Prevent propagation to root logger if file handler is set,
    # so audit logs only go to the audit file
    if audit_file:
        audit_logger.propagate = False

    audit_logger.info(
        '"event": "audit_init", "audit_file": "%s"',
        audit_file or "stderr",
    )


def is_audit_enabled() -> bool:
    """Check if audit logging is enabled."""
    return _AUDIT_ENABLED


def log_tool_invocation(
    tool_name: str,
    *,
    stream: str | None = None,
    query: str | None = None,
    identity: str | None = None,
    blocked: bool = False,
    reason: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Log a tool invocation for audit purposes.

    Args:
        tool_name: Name of the MCP tool invoked
        stream: Channel/stream accessed (if applicable)
        query: Search query (if applicable)
        identity: User or bot identity
        blocked: Whether the invocation was blocked by policy
        reason: Reason for blocking (if blocked)
        extra: Additional metadata
    """
    if not _AUDIT_ENABLED:
        return

    parts = [
        '"event": "tool_invocation"',
        f'"tool": "{tool_name}"',
        f'"timestamp_unix": {time.time():.3f}',
    ]

    if stream is not None:
        parts.append(f'"stream": "{stream}"')
    if query is not None:
        # Truncate long queries for log readability
        q = query[:200] + "..." if len(query) > 200 else query
        # Escape quotes in query
        q = q.replace('"', '\\"')
        parts.append(f'"query": "{q}"')
    if identity is not None:
        parts.append(f'"identity": "{identity}"')
    if blocked:
        parts.append('"blocked": true')
        if reason:
            parts.append(f'"reason": "{reason}"')
    if extra:
        for k, v in extra.items():
            parts.append(f'"{k}": "{v}"')

    audit_logger.info(", ".join(parts))


def log_channel_access(
    channel_name: str,
    access_type: str,
    *,
    identity: str | None = None,
    message_count: int | None = None,
) -> None:
    """Log a channel access event.

    Args:
        channel_name: Name of the channel accessed
        access_type: Type of access (read, search, send, list_topics)
        identity: User or bot identity
        message_count: Number of messages returned (if applicable)
    """
    if not _AUDIT_ENABLED:
        return

    parts = [
        '"event": "channel_access"',
        f'"channel": "{channel_name}"',
        f'"access_type": "{access_type}"',
        f'"timestamp_unix": {time.time():.3f}',
    ]

    if identity is not None:
        parts.append(f'"identity": "{identity}"')
    if message_count is not None:
        parts.append(f'"message_count": {message_count}')

    audit_logger.info(", ".join(parts))
