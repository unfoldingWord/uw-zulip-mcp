"""Tests for the audit logging module."""

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
                log_tool_invocation("send_message", stream="30 Infrastructure")
            assert len(caplog.records) == 0
        finally:
            audit_mod._AUDIT_ENABLED = original

    def test_log_tool_invocation_when_enabled(self, caplog):
        """When audit is enabled, tool invocation is logged."""
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
            assert any("search_messages" in r.message for r in caplog.records)
            assert any("deployment status" in r.message for r in caplog.records)
        finally:
            audit_mod._AUDIT_ENABLED = original

    def test_log_blocked_invocation(self, caplog):
        """Blocked invocations include reason."""
        import zulipchat_mcp.core.audit as audit_mod

        original = audit_mod._AUDIT_ENABLED
        audit_mod._AUDIT_ENABLED = True
        try:
            with caplog.at_level(logging.DEBUG, logger="zulipchat_mcp.audit"):
                log_tool_invocation(
                    "send_message",
                    stream="00.16 Prayer Requests",
                    blocked=True,
                    reason="channel_filter",
                )
            assert any("blocked" in r.message for r in caplog.records)
            assert any("channel_filter" in r.message for r in caplog.records)
        finally:
            audit_mod._AUDIT_ENABLED = original

    def test_log_channel_access_when_enabled(self, caplog):
        """Channel access events are logged."""
        import zulipchat_mcp.core.audit as audit_mod

        original = audit_mod._AUDIT_ENABLED
        audit_mod._AUDIT_ENABLED = True
        try:
            with caplog.at_level(logging.DEBUG, logger="zulipchat_mcp.audit"):
                log_channel_access(
                    "30 Infrastructure", "read",
                    identity="user", message_count=42,
                )
            assert any("30 Infrastructure" in r.message for r in caplog.records)
            assert any("channel_access" in r.message for r in caplog.records)
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
            # Should be truncated to 200 + "..."
            records = [r for r in caplog.records if "search_messages" in r.message]
            assert len(records) == 1
            assert "..." in records[0].message
            assert "x" * 201 not in records[0].message
        finally:
            audit_mod._AUDIT_ENABLED = original
