"""Tests for the audit logging module."""

import json
import logging

from zulipchat_mcp.core.audit import (
    log_channel_access,
    log_tool_invocation,
)


class TestAuditLogging:
    def test_log_tool_invocation_when_disabled(self, caplog):
        """When audit is disabled, no log output."""
        import zulipchat_mcp.core.audit as audit_mod

        original = audit_mod._AUDIT_ENABLED
        audit_mod._AUDIT_ENABLED = False
        try:
            with caplog.at_level(logging.DEBUG, logger="zulipchat_mcp.audit"):
                log_tool_invocation("send_message", stream="30 Platform Operations")
            assert len(caplog.records) == 0
        finally:
            audit_mod._AUDIT_ENABLED = original

    def test_log_tool_invocation_when_enabled(self, caplog):
        """When audit is enabled, tool invocation is logged as valid JSON."""
        import zulipchat_mcp.core.audit as audit_mod

        original = audit_mod._AUDIT_ENABLED
        audit_mod._AUDIT_ENABLED = True
        try:
            with caplog.at_level(logging.DEBUG, logger="zulipchat_mcp.audit"):
                log_tool_invocation(
                    "search_messages",
                    query="deployment status",
                    identity="user",
                )
            records = [r for r in caplog.records if "search_messages" in r.message]
            assert len(records) == 1
            # Verify it's valid JSON
            event = json.loads(records[0].message)
            assert event["tool"] == "search_messages"
            assert event["query"] == "deployment status"
            assert event["identity"] == "user"
            assert "timestamp_unix" in event
        finally:
            audit_mod._AUDIT_ENABLED = original

    def test_log_blocked_invocation(self, caplog):
        """Blocked invocations include reason in structured JSON."""
        import zulipchat_mcp.core.audit as audit_mod

        original = audit_mod._AUDIT_ENABLED
        audit_mod._AUDIT_ENABLED = True
        try:
            with caplog.at_level(logging.DEBUG, logger="zulipchat_mcp.audit"):
                log_tool_invocation(
                    "send_message",
                    stream="00.16 Personal Updates",
                    blocked=True,
                    reason="channel_filter",
                )
            records = [r for r in caplog.records if "send_message" in r.message]
            assert len(records) == 1
            event = json.loads(records[0].message)
            assert event["blocked"] is True
            assert event["reason"] == "channel_filter"
        finally:
            audit_mod._AUDIT_ENABLED = original

    def test_log_channel_access_when_enabled(self, caplog):
        """Channel access events are logged as valid JSON."""
        import zulipchat_mcp.core.audit as audit_mod

        original = audit_mod._AUDIT_ENABLED
        audit_mod._AUDIT_ENABLED = True
        try:
            with caplog.at_level(logging.DEBUG, logger="zulipchat_mcp.audit"):
                log_channel_access(
                    "30 Platform Operations",
                    "read",
                    identity="user",
                    message_count=42,
                )
            records = [
                r for r in caplog.records if "30 Platform Operations" in r.message
            ]
            assert len(records) == 1
            event = json.loads(records[0].message)
            assert event["channel"] == "30 Platform Operations"
            assert event["access_type"] == "read"
            assert event["message_count"] == 42
        finally:
            audit_mod._AUDIT_ENABLED = original

    def test_long_query_truncated(self, caplog):
        """Long search queries are truncated in audit logs."""
        import zulipchat_mcp.core.audit as audit_mod

        original = audit_mod._AUDIT_ENABLED
        audit_mod._AUDIT_ENABLED = True
        try:
            long_query = "x" * 300
            with caplog.at_level(logging.DEBUG, logger="zulipchat_mcp.audit"):
                log_tool_invocation("search_messages", query=long_query)
            records = [r for r in caplog.records if "search_messages" in r.message]
            assert len(records) == 1
            event = json.loads(records[0].message)
            assert event["query"].endswith("...")
            assert len(event["query"]) == 203  # 200 chars + "..."
        finally:
            audit_mod._AUDIT_ENABLED = original

    def test_injection_safe_stream_name(self, caplog):
        """Stream names with special characters don't break JSON."""
        import zulipchat_mcp.core.audit as audit_mod

        original = audit_mod._AUDIT_ENABLED
        audit_mod._AUDIT_ENABLED = True
        try:
            evil_name = '00.16 Personal", "injected": "true'
            with caplog.at_level(logging.DEBUG, logger="zulipchat_mcp.audit"):
                log_tool_invocation("send_message", stream=evil_name)
            records = [r for r in caplog.records if "send_message" in r.message]
            assert len(records) == 1
            # Must parse as valid JSON without injection
            event = json.loads(records[0].message)
            assert event["stream"] == evil_name
            assert "injected" not in event
        finally:
            audit_mod._AUDIT_ENABLED = original

    def test_injection_safe_newlines(self, caplog):
        """Newlines in values don't create extra log lines."""
        import zulipchat_mcp.core.audit as audit_mod

        original = audit_mod._AUDIT_ENABLED
        audit_mod._AUDIT_ENABLED = True
        try:
            evil_query = 'search\n{"injected": true}'
            with caplog.at_level(logging.DEBUG, logger="zulipchat_mcp.audit"):
                log_tool_invocation("search_messages", query=evil_query)
            records = [r for r in caplog.records if "search_messages" in r.message]
            assert len(records) == 1
            event = json.loads(records[0].message)
            assert event["query"] == evil_query
        finally:
            audit_mod._AUDIT_ENABLED = original

    def test_init_idempotent(self):
        """Calling init_audit_logging multiple times doesn't duplicate handlers."""
        import zulipchat_mcp.core.audit as audit_mod

        original_enabled = audit_mod._AUDIT_ENABLED
        original_handlers = list(audit_mod.audit_logger.handlers)
        try:
            import os

            os.environ["ZULIPCHAT_AUDIT_ENABLED"] = "true"
            # Don't set ZULIPCHAT_AUDIT_FILE to avoid filesystem side effects

            audit_mod.init_audit_logging()
            audit_mod.init_audit_logging()
            audit_mod.init_audit_logging()

            # No file handlers should be added (no AUDIT_FILE set)
            file_handlers = [
                h
                for h in audit_mod.audit_logger.handlers
                if isinstance(h, logging.FileHandler)
            ]
            assert len(file_handlers) == 0
        finally:
            audit_mod._AUDIT_ENABLED = original_enabled
            audit_mod.audit_logger.handlers = original_handlers
            os.environ.pop("ZULIPCHAT_AUDIT_ENABLED", None)
