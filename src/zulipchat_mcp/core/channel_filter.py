"""Channel filtering based on Johnny Decimal naming conventions.

Provides deterministic, taxonomy-based access control for Zulip channels.
Channels are filtered by their JD prefix (XX or XX.YY format), with support
for area-range allowlists/denylists and individual channel overrides.

Filter is enforced at the client wrapper level via both name and stream-ID
based guards so no tool can bypass it.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Matches JD prefixes: "30 Infrastructure", "42.01 Hebrew Grammar", "00.16 Prayer Requests"
JD_PREFIX_PATTERN = re.compile(r"^(\d{2})(?:\.(\d{2}))?\s")

# Counter for blocked-by-policy events (for observability)
_blocked_counts: dict[str, int] = {"send": 0, "read": 0, "stream_list": 0, "stream_id": 0}


def get_blocked_counts() -> dict[str, int]:
    """Get current blocked-by-policy counters."""
    return dict(_blocked_counts)


def _increment_blocked(category: str) -> None:
    """Increment a blocked-by-policy counter and log."""
    _blocked_counts[category] = _blocked_counts.get(category, 0) + 1


@dataclass
class ChannelFilterConfig:
    """Parsed channel filter configuration."""

    enabled: bool = False
    jd_allow_areas: list[tuple[int, int]] = field(default_factory=list)
    jd_deny_areas: list[tuple[int, int]] = field(default_factory=list)
    channel_include: set[str] = field(default_factory=set)
    channel_exclude: set[str] = field(default_factory=set)
    exclude_non_jd: bool = True
    exclude_dms: bool = True
    exclude_private: bool = True


def parse_area_ranges(spec: str) -> list[tuple[int, int]]:
    """Parse area range specification into (min, max) tuples.

    Raises ValueError with a descriptive message on malformed input.

    Examples:
        "30-99" -> [(30, 99)]
        "01,02,14,30-99" -> [(1, 1), (2, 2), (14, 14), (30, 99)]
        "" -> []
    """
    if not spec or not spec.strip():
        return []

    ranges: list[tuple[int, int]] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if "-" in part:
                lo, hi = part.split("-", 1)
                ranges.append((int(lo.strip()), int(hi.strip())))
            else:
                val = int(part.strip())
                ranges.append((val, val))
        except ValueError as e:
            raise ValueError(
                f"Invalid JD area range '{part}' — expected format like '30-99' or '42'. "
                f"Check your ZULIPCHAT_JD_ALLOW_AREAS / ZULIPCHAT_JD_DENY_AREAS env vars."
            ) from e
    return ranges


def parse_channel_list(spec: str) -> set[str]:
    """Parse comma-separated channel names into a set.

    Channel names are stripped but case-preserved (Zulip channels are case-sensitive).
    """
    if not spec or not spec.strip():
        return set()
    return {name.strip() for name in spec.split(",") if name.strip()}


def parse_jd_prefix(channel_name: str) -> tuple[int, int | None] | None:
    """Extract JD area and optional category from a channel name.

    Returns:
        (area, category) tuple, or (area, None) if no category, or None if no JD prefix.

    Examples:
        "30 Infrastructure" -> (30, None)
        "42.01 Hebrew Grammar" -> (42, 1)
        "00.16 Prayer Requests" -> (0, 16)
        "general" -> None
        "Helpdesk - ST" -> None
    """
    match = JD_PREFIX_PATTERN.match(channel_name)
    if not match:
        return None
    area = int(match.group(1))
    category = int(match.group(2)) if match.group(2) else None
    return (area, category)


def _in_ranges(value: int, ranges: list[tuple[int, int]]) -> bool:
    """Check if a value falls within any of the given ranges."""
    return any(lo <= value <= hi for lo, hi in ranges)


class ChannelFilter:
    """Filters Zulip channels based on JD naming conventions.

    Maintains a stream metadata index (populated from get_streams results)
    to enable consistent enforcement across both name-based and ID-based access.

    Evaluation order for a channel name:
    1. If in channel_exclude -> DENY (highest priority)
    2. If in channel_include -> ALLOW
    3. Parse JD prefix. If no prefix and exclude_non_jd -> DENY
    4. If JD prefix, check deny_areas -> DENY
    5. If allow_areas is set, check if area is in allowed ranges -> DENY if not
    6. Otherwise -> ALLOW
    """

    def __init__(self, config: ChannelFilterConfig) -> None:
        self.config = config
        # Stream metadata index: id -> {"name": str, "invite_only": bool}
        self._stream_index: dict[int, dict[str, Any]] = {}
        if config.enabled:
            logger.info(
                "Channel filter enabled: allow_areas=%s, deny_areas=%s, "
                "include=%d channels, exclude=%d channels, "
                "exclude_non_jd=%s, exclude_dms=%s, exclude_private=%s",
                config.jd_allow_areas,
                config.jd_deny_areas,
                len(config.channel_include),
                len(config.channel_exclude),
                config.exclude_non_jd,
                config.exclude_dms,
                config.exclude_private,
            )

    def update_stream_index(self, streams: list[dict[str, Any]]) -> None:
        """Update the stream metadata index from a list of stream dicts.

        Called after fetching streams from the API (before filtering) so the
        index contains ALL streams, not just allowed ones. This enables
        ID-based lookups for enforcement.
        """
        for s in streams:
            stream_id = s.get("stream_id")
            if stream_id is not None:
                self._stream_index[stream_id] = {
                    "name": s.get("name", ""),
                    "invite_only": s.get("invite_only", False),
                }

    def is_stream_id_allowed(self, stream_id: int) -> bool:
        """Check if a stream ID passes the filter.

        Uses the stream metadata index to resolve ID to name and check
        both the name filter and private channel exclusion.

        Returns True if:
        - Filter is disabled
        - Stream ID is not in the index (fail-open for unknown IDs to avoid
          breaking tools when index hasn't been populated yet — the stream
          listing filter prevents discovery of blocked IDs)
        """
        if not self.config.enabled:
            return True

        meta = self._stream_index.get(stream_id)
        if meta is None:
            # Unknown stream ID — not in our index. Log and allow to avoid
            # breaking tools before cache warmup. The stream listing filter
            # prevents discovery of blocked stream IDs in normal operation.
            logger.debug(
                "Stream ID %d not in filter index, allowing (index size: %d)",
                stream_id,
                len(self._stream_index),
            )
            return True

        # Check private exclusion
        if self.config.exclude_private and meta.get("invite_only", False):
            _increment_blocked("stream_id")
            logger.warning(
                "Blocked stream ID %d (%s): private channel excluded by policy",
                stream_id,
                meta.get("name", "unknown"),
            )
            return False

        name = meta.get("name", "")
        allowed = self.is_channel_allowed(name)
        if not allowed:
            _increment_blocked("stream_id")
            logger.warning(
                "Blocked stream ID %d (%s): channel excluded by policy",
                stream_id,
                name,
            )
        return allowed

    def is_channel_allowed(self, channel_name: str) -> bool:
        """Check if a channel name passes the filter.

        Returns True if the channel is allowed, False if it should be excluded.
        When filtering is disabled, always returns True.

        Note: This checks the JD name filter only. For private channel exclusion
        on name-based paths, use is_channel_allowed_with_privacy() when stream
        metadata is available.
        """
        if not self.config.enabled:
            return True

        # 1. Explicit exclude takes absolute precedence
        if channel_name in self.config.channel_exclude:
            return False

        # 2. Explicit include overrides everything else
        if channel_name in self.config.channel_include:
            return True

        # 3. Parse JD prefix
        jd = parse_jd_prefix(channel_name)

        if jd is None:
            # No JD prefix — respect exclude_non_jd setting
            return not self.config.exclude_non_jd

        area, _category = jd

        # 4. Check deny areas
        if self.config.jd_deny_areas and _in_ranges(area, self.config.jd_deny_areas):
            return False

        # 5. Check allow areas (if set, only allowed areas pass)
        if self.config.jd_allow_areas:
            return _in_ranges(area, self.config.jd_allow_areas)

        # 6. No allow_areas restriction — all JD channels pass
        return True

    def is_channel_allowed_with_privacy(self, channel_name: str) -> bool:
        """Check channel name AND private status using stream index.

        Falls back to is_channel_allowed() if stream is not in the index.
        """
        if not self.config.enabled:
            return True

        # Look up private status from index by name
        if self.config.exclude_private:
            for meta in self._stream_index.values():
                if meta.get("name") == channel_name:
                    if meta.get("invite_only", False):
                        return False
                    break

        return self.is_channel_allowed(channel_name)

    def is_stream_allowed(self, stream: dict[str, Any]) -> bool:
        """Check if a stream dict passes the filter.

        Handles both channel name filtering and private channel exclusion.
        """
        if not self.config.enabled:
            return True

        # Exclude private channels if configured
        if self.config.exclude_private and stream.get("invite_only", False):
            return False

        name = stream.get("name", "")
        return self.is_channel_allowed(name)

    def filter_streams(self, streams: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Filter a list of stream dicts, removing excluded channels."""
        if not self.config.enabled:
            return streams
        before = len(streams)
        result = [s for s in streams if self.is_stream_allowed(s)]
        blocked = before - len(result)
        if blocked > 0:
            _blocked_counts["stream_list"] = _blocked_counts.get("stream_list", 0) + blocked
        return result

    def filter_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Filter a list of message dicts, removing messages from excluded channels.

        Checks both JD name rules and private channel status for stream messages.
        DM messages are handled by the exclude_dms setting.
        """
        if not self.config.enabled:
            return messages

        filtered = []
        for msg in messages:
            msg_type = msg.get("type", "")

            # Handle DMs
            if msg_type == "private":
                if not self.config.exclude_dms:
                    filtered.append(msg)
                else:
                    _increment_blocked("read")
                continue

            # Stream messages — check channel name AND privacy
            recipient = msg.get("display_recipient", "")
            if isinstance(recipient, str) and self.is_channel_allowed_with_privacy(recipient):
                filtered.append(msg)
            elif isinstance(recipient, str):
                _increment_blocked("read")

        return filtered


def load_filter_config_from_env() -> ChannelFilterConfig:
    """Load channel filter configuration from environment variables.

    Raises ValueError if area range env vars contain malformed values.
    The server should catch this and fail with a clear message.

    Environment variables:
        ZULIPCHAT_CHANNEL_FILTER_ENABLED: "true" to enable (default: false)
        ZULIPCHAT_JD_ALLOW_AREAS: Comma-separated area ranges (e.g., "01,02,14,30-99")
        ZULIPCHAT_JD_DENY_AREAS: Comma-separated area ranges to deny
        ZULIPCHAT_CHANNEL_INCLUDE: Comma-separated channel names to always include
        ZULIPCHAT_CHANNEL_EXCLUDE: Comma-separated channel names to always exclude
        ZULIPCHAT_EXCLUDE_NON_JD: "true" to exclude non-JD channels (default: true)
        ZULIPCHAT_EXCLUDE_DMS: "true" to exclude DMs (default: true)
        ZULIPCHAT_EXCLUDE_PRIVATE: "true" to exclude private channels (default: true)
    """

    def _bool_env(key: str, default: bool = True) -> bool:
        val = os.getenv(key, "").lower()
        if not val:
            return default
        return val in ("true", "1", "yes", "on")

    return ChannelFilterConfig(
        enabled=_bool_env("ZULIPCHAT_CHANNEL_FILTER_ENABLED", default=False),
        jd_allow_areas=parse_area_ranges(os.getenv("ZULIPCHAT_JD_ALLOW_AREAS", "")),
        jd_deny_areas=parse_area_ranges(os.getenv("ZULIPCHAT_JD_DENY_AREAS", "")),
        channel_include=parse_channel_list(os.getenv("ZULIPCHAT_CHANNEL_INCLUDE", "")),
        channel_exclude=parse_channel_list(os.getenv("ZULIPCHAT_CHANNEL_EXCLUDE", "")),
        exclude_non_jd=_bool_env("ZULIPCHAT_EXCLUDE_NON_JD", default=True),
        exclude_dms=_bool_env("ZULIPCHAT_EXCLUDE_DMS", default=True),
        exclude_private=_bool_env("ZULIPCHAT_EXCLUDE_PRIVATE", default=True),
    )


# Module-level singleton
_channel_filter: ChannelFilter | None = None


def init_channel_filter(config: ChannelFilterConfig | None = None) -> ChannelFilter:
    """Initialize the global channel filter singleton.

    Args:
        config: Optional pre-built config. If None, loads from environment.

    Returns:
        The initialized ChannelFilter instance.

    Raises:
        ValueError: If environment variables contain malformed area ranges.
    """
    global _channel_filter
    if config is None:
        config = load_filter_config_from_env()
    _channel_filter = ChannelFilter(config)
    return _channel_filter


def get_channel_filter() -> ChannelFilter:
    """Get the global channel filter singleton.

    If not initialized, creates a default (disabled) filter.
    """
    global _channel_filter
    if _channel_filter is None:
        _channel_filter = ChannelFilter(ChannelFilterConfig())
    return _channel_filter


def is_channel_allowed(channel_name: str) -> bool:
    """Convenience function to check if a channel is allowed."""
    return get_channel_filter().is_channel_allowed(channel_name)
