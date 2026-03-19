"""Channel filtering based on Johnny Decimal naming conventions.

Provides deterministic, taxonomy-based access control for Zulip channels.
Channels are filtered by their JD prefix (XX or XX.YY format), with support
for area-range allowlists/denylists and individual channel overrides.

Filter is enforced at the client wrapper level so no tool can bypass it.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Matches JD prefixes: "30 Infrastructure", "42.01 Hebrew Grammar", "00.16 Prayer Requests"
JD_PREFIX_PATTERN = re.compile(r"^(\d{2})(?:\.(\d{2}))?\s")


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
        if "-" in part:
            lo, hi = part.split("-", 1)
            ranges.append((int(lo.strip()), int(hi.strip())))
        else:
            val = int(part.strip())
            ranges.append((val, val))
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

    def is_channel_allowed(self, channel_name: str) -> bool:
        """Check if a channel name passes the filter.

        Returns True if the channel is allowed, False if it should be excluded.
        When filtering is disabled, always returns True.
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

    def is_stream_allowed(self, stream: dict) -> bool:
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

    def filter_streams(self, streams: list[dict]) -> list[dict]:
        """Filter a list of stream dicts, removing excluded channels."""
        if not self.config.enabled:
            return streams
        return [s for s in streams if self.is_stream_allowed(s)]

    def filter_messages(self, messages: list[dict]) -> list[dict]:
        """Filter a list of message dicts, removing messages from excluded channels.

        Only filters stream-type messages. Private/DM messages are handled
        by the exclude_dms setting.
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
                continue

            # Stream messages — check channel name
            recipient = msg.get("display_recipient", "")
            if isinstance(recipient, str) and self.is_channel_allowed(recipient):
                filtered.append(msg)

        return filtered


def load_filter_config_from_env() -> ChannelFilterConfig:
    """Load channel filter configuration from environment variables.

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
