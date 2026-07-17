"""Audit logging for MCP tool invocations.

Logs which tools were invoked, which channels were accessed, and what
searches were performed — but never logs message content. Designed for
organizational accountability and incident response.

Audit events are emitted via Python's standard logging at a configurable
level (default: INFO) to a dedicated "zulipchat_mcp.audit" logger. This
allows operators to route audit logs to a separate file or service via
standard logging configuration.

All event fields are serialized via json.dumps to prevent log injection.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

# Dedicated audit logger — separate from application logs so operators
# can route it independently (e.g., to a file, syslog, or SIEM)
audit_logger = logging.getLogger("zulipchat_mcp.audit")

_AUDIT_ENABLED: bool = False
_AUDIT_INITIALIZED: bool = False


def init_audit_logging() -> None:
    """Initialize audit logging from environment configuration.

    Idempotent — safe to call multiple times. Subsequent calls reconfigure
    without duplicating handlers.

    Environment variables:
        ZULIPCHAT_AUDIT_ENABLED: "true" to enable (default: false)
        ZULIPCHAT_AUDIT_FILE: Path to audit log file (optional)
        ZULIPCHAT_AUDIT_LEVEL: Log level for audit events (default: INFO)
    """
    global _AUDIT_ENABLED, _AUDIT_INITIALIZED

    enabled = os.getenv("ZULIPCHAT_AUDIT_ENABLED", "").lower()
    _AUDIT_ENABLED = enabled in ("true", "1", "yes", "on")

    if not _AUDIT_ENABLED:
        return

    level_str = os.getenv("ZULIPCHAT_AUDIT_LEVEL", "INFO").upper()
    level = getattr(logging, level_str, logging.INFO)
    audit_logger.setLevel(level)

    # Guard against duplicate handlers on re-init
    audit_file = os.getenv("ZULIPCHAT_AUDIT_FILE")
    if audit_file:
        # Remove any existing file handlers to prevent duplicates
        for h in list(audit_logger.handlers):
            if isinstance(h, logging.FileHandler):
                audit_logger.removeHandler(h)
                h.close()

        handler = logging.FileHandler(audit_file)
        handler.setFormatter(logging.Formatter("%(message)s"))
        audit_logger.addHandler(handler)
        audit_logger.propagate = False

    _AUDIT_INITIALIZED = True

    _log_event({"event": "audit_init", "audit_file": audit_file or "stderr"})


def is_audit_enabled() -> bool:
    """Check if audit logging is enabled."""
    return _AUDIT_ENABLED


def _log_event(event: dict[str, Any]) -> None:
    """Serialize and log an audit event dict as JSON.

    All values are serialized via json.dumps to prevent log injection.
    In hosted mode, every event is stamped with the authenticated request
    user's email (never the API key) for per-user accountability.
    """
    from .request_credentials import get_request_credentials

    creds = get_request_credentials()
    if creds is not None:
        event.setdefault("request_user", creds.email)
    event["timestamp_unix"] = round(time.time(), 3)
    audit_logger.info(json.dumps(event, default=str))


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

    event: dict[str, Any] = {
        "event": "tool_invocation",
        "tool": tool_name,
    }

    if stream is not None:
        event["stream"] = stream
    if query is not None:
        # Truncate long queries for log readability
        event["query"] = query[:200] + "..." if len(query) > 200 else query
    if identity is not None:
        event["identity"] = identity
    if blocked:
        event["blocked"] = True
        if reason:
            event["reason"] = reason
    if extra:
        event.update(extra)

    _log_event(event)


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

    event: dict[str, Any] = {
        "event": "channel_access",
        "channel": channel_name,
        "access_type": access_type,
    }

    if identity is not None:
        event["identity"] = identity
    if message_count is not None:
        event["message_count"] = message_count

    _log_event(event)
