"""Tests for the channel filter module."""

import pytest

from zulipchat_mcp.core.channel_filter import (
    ChannelFilter,
    ChannelFilterConfig,
    get_blocked_counts,
    parse_area_ranges,
    parse_channel_list,
    parse_jd_prefix,
)

# --- parse_jd_prefix tests ---


class TestParseJdPrefix:
    def test_area_only(self):
        assert parse_jd_prefix("30 Infrastructure") == (30, None)

    def test_area_and_category(self):
        assert parse_jd_prefix("42.01 Hebrew Grammar") == (42, 1)

    def test_zero_prefixed(self):
        assert parse_jd_prefix("00.16 Prayer Requests") == (0, 16)

    def test_no_prefix(self):
        assert parse_jd_prefix("general") is None

    def test_no_prefix_with_dash(self):
        assert parse_jd_prefix("Helpdesk - ST") is None

    def test_no_space_after_number(self):
        # "30Infrastructure" should not match — requires space after prefix
        assert parse_jd_prefix("30Infrastructure") is None

    def test_three_digit_area(self):
        # JD areas are two digits only
        assert parse_jd_prefix("100 Something") is None

    def test_single_digit(self):
        assert parse_jd_prefix("3 Something") is None

    def test_area_with_hyphen_id(self):
        # "14.17 - 2024 LNT Lease Payments" — JD ID followed by number with hyphen
        result = parse_jd_prefix("14.17 - 2024 LNT Lease Payments")
        assert result == (14, 17)

    def test_area_folder_format(self):
        # "80-89 Tech & SLR" — this is a Zulip folder, not a channel
        # It has a dash in the number, so it shouldn't match JD prefix
        assert parse_jd_prefix("80-89 Tech & SLR") is None


# --- parse_area_ranges tests ---


class TestParseAreaRanges:
    def test_single_range(self):
        assert parse_area_ranges("30-99") == [(30, 99)]

    def test_multiple_ranges(self):
        assert parse_area_ranges("01,02,14,30-99") == [
            (1, 1),
            (2, 2),
            (14, 14),
            (30, 99),
        ]

    def test_empty_string(self):
        assert parse_area_ranges("") == []

    def test_none_like(self):
        assert parse_area_ranges("  ") == []

    def test_single_value(self):
        assert parse_area_ranges("42") == [(42, 42)]

    def test_with_spaces(self):
        assert parse_area_ranges(" 30 - 99 , 01 ") == [(30, 99), (1, 1)]


# --- parse_channel_list tests ---


class TestParseChannelList:
    def test_basic(self):
        result = parse_channel_list("general,random")
        assert result == {"general", "random"}

    def test_with_spaces(self):
        result = parse_channel_list(" 00.17 All unfoldingWord , Helpdesk - ST ")
        assert "00.17 All unfoldingWord" in result
        assert "Helpdesk - ST" in result

    def test_empty(self):
        assert parse_channel_list("") == set()

    def test_none(self):
        assert parse_channel_list("  ") == set()


# --- ChannelFilter tests ---


class TestChannelFilterDisabled:
    def test_all_channels_pass_when_disabled(self):
        cf = ChannelFilter(ChannelFilterConfig(enabled=False))
        assert cf.is_channel_allowed("anything") is True
        assert cf.is_channel_allowed("00.16 Prayer Requests") is True

    def test_filter_streams_noop_when_disabled(self):
        cf = ChannelFilter(ChannelFilterConfig(enabled=False))
        streams = [{"name": "anything"}, {"name": "00.16 Prayer Requests"}]
        assert cf.filter_streams(streams) == streams


class TestChannelFilterExclude:
    def test_explicit_exclude_takes_precedence(self):
        cf = ChannelFilter(
            ChannelFilterConfig(
                enabled=True,
                channel_exclude={"00.16 Prayer Requests"},
                jd_allow_areas=[(0, 99)],
            )
        )
        assert cf.is_channel_allowed("00.16 Prayer Requests") is False

    def test_exclude_overrides_include(self):
        cf = ChannelFilter(
            ChannelFilterConfig(
                enabled=True,
                channel_include={"00.16 Prayer Requests"},
                channel_exclude={"00.16 Prayer Requests"},
            )
        )
        # Exclude takes absolute precedence
        assert cf.is_channel_allowed("00.16 Prayer Requests") is False


class TestChannelFilterInclude:
    def test_explicit_include(self):
        cf = ChannelFilter(
            ChannelFilterConfig(
                enabled=True,
                channel_include={"Helpdesk - ST"},
                exclude_non_jd=True,
            )
        )
        # Non-JD channel, would normally be excluded, but explicitly included
        assert cf.is_channel_allowed("Helpdesk - ST") is True

    def test_include_overrides_area_deny(self):
        cf = ChannelFilter(
            ChannelFilterConfig(
                enabled=True,
                channel_include={"00.17 All unfoldingWord"},
                jd_deny_areas=[(0, 9)],
            )
        )
        assert cf.is_channel_allowed("00.17 All unfoldingWord") is True


class TestChannelFilterJdAreas:
    def test_allow_areas(self):
        cf = ChannelFilter(
            ChannelFilterConfig(
                enabled=True,
                jd_allow_areas=[(30, 99)],
            )
        )
        assert cf.is_channel_allowed("30 Infrastructure") is True
        assert cf.is_channel_allowed("84 BT Servant") is True
        assert cf.is_channel_allowed("01 Knowledge base") is False

    def test_deny_areas(self):
        cf = ChannelFilter(
            ChannelFilterConfig(
                enabled=True,
                jd_deny_areas=[(0, 9)],
            )
        )
        assert cf.is_channel_allowed("00.16 Prayer Requests") is False
        assert cf.is_channel_allowed("30 Infrastructure") is True

    def test_deny_overrides_allow(self):
        cf = ChannelFilter(
            ChannelFilterConfig(
                enabled=True,
                jd_allow_areas=[(0, 99)],
                jd_deny_areas=[(0, 9)],
            )
        )
        assert cf.is_channel_allowed("00.16 Prayer Requests") is False
        assert cf.is_channel_allowed("30 Infrastructure") is True

    def test_no_allow_areas_allows_all_jd(self):
        cf = ChannelFilter(
            ChannelFilterConfig(
                enabled=True,
                jd_allow_areas=[],
            )
        )
        assert cf.is_channel_allowed("01 Knowledge base") is True
        assert cf.is_channel_allowed("99 Archive") is True


class TestChannelFilterNonJd:
    def test_exclude_non_jd_by_default(self):
        cf = ChannelFilter(
            ChannelFilterConfig(
                enabled=True,
                exclude_non_jd=True,
            )
        )
        assert cf.is_channel_allowed("Helpdesk - ST") is False
        assert cf.is_channel_allowed("Catalyst Luncheon") is False

    def test_include_non_jd_when_configured(self):
        cf = ChannelFilter(
            ChannelFilterConfig(
                enabled=True,
                exclude_non_jd=False,
            )
        )
        assert cf.is_channel_allowed("Helpdesk - ST") is True


class TestChannelFilterPrivateStreams:
    def test_exclude_private_streams(self):
        cf = ChannelFilter(
            ChannelFilterConfig(
                enabled=True,
                exclude_private=True,
                jd_allow_areas=[(0, 99)],
            )
        )
        stream = {"name": "09.40 - 2026 All Staff", "invite_only": True}
        assert cf.is_stream_allowed(stream) is False

    def test_allow_private_when_configured(self):
        cf = ChannelFilter(
            ChannelFilterConfig(
                enabled=True,
                exclude_private=False,
                jd_allow_areas=[(0, 99)],
            )
        )
        stream = {"name": "09.40 - 2026 All Staff", "invite_only": True}
        assert cf.is_stream_allowed(stream) is True

    def test_public_stream_not_affected(self):
        cf = ChannelFilter(
            ChannelFilterConfig(
                enabled=True,
                exclude_private=True,
                jd_allow_areas=[(0, 99)],
            )
        )
        stream = {"name": "30 Infrastructure", "invite_only": False}
        assert cf.is_stream_allowed(stream) is True


class TestFilterStreams:
    def test_filters_excluded_streams(self):
        cf = ChannelFilter(
            ChannelFilterConfig(
                enabled=True,
                jd_allow_areas=[(30, 99)],
                channel_exclude={"00.16 Prayer Requests"},
            )
        )
        streams = [
            {"name": "30 Infrastructure", "invite_only": False},
            {"name": "00.16 Prayer Requests", "invite_only": False},
            {"name": "84 BT Servant", "invite_only": False},
            {"name": "Helpdesk - ST", "invite_only": False},
        ]
        result = cf.filter_streams(streams)
        names = [s["name"] for s in result]
        assert "30 Infrastructure" in names
        assert "84 BT Servant" in names
        assert "00.16 Prayer Requests" not in names
        assert "Helpdesk - ST" not in names


class TestFilterMessages:
    def test_filters_stream_messages(self):
        cf = ChannelFilter(
            ChannelFilterConfig(
                enabled=True,
                jd_allow_areas=[(30, 99)],
            )
        )
        messages = [
            {"type": "stream", "display_recipient": "30 Infrastructure", "content": "ok"},
            {"type": "stream", "display_recipient": "00.16 Prayer Requests", "content": "pray"},
            {"type": "stream", "display_recipient": "84 BT Servant", "content": "hi"},
        ]
        result = cf.filter_messages(messages)
        recipients = [m["display_recipient"] for m in result]
        assert "30 Infrastructure" in recipients
        assert "84 BT Servant" in recipients
        assert "00.16 Prayer Requests" not in recipients

    def test_excludes_dms_when_configured(self):
        cf = ChannelFilter(
            ChannelFilterConfig(
                enabled=True,
                exclude_dms=True,
            )
        )
        messages = [
            {"type": "private", "display_recipient": [{"email": "a@b.com"}], "content": "dm"},
            {"type": "stream", "display_recipient": "30 Infrastructure", "content": "ok"},
        ]
        result = cf.filter_messages(messages)
        assert len(result) == 1
        assert result[0]["type"] == "stream"

    def test_includes_dms_when_configured(self):
        cf = ChannelFilter(
            ChannelFilterConfig(
                enabled=True,
                exclude_dms=False,
            )
        )
        messages = [
            {"type": "private", "display_recipient": [{"email": "a@b.com"}], "content": "dm"},
        ]
        result = cf.filter_messages(messages)
        assert len(result) == 1


class TestRealisticConfig:
    """Tests with a configuration matching the unfoldingWord deployment."""

    @pytest.fixture
    def uw_filter(self):
        return ChannelFilter(
            ChannelFilterConfig(
                enabled=True,
                jd_allow_areas=[(1, 2), (14, 14), (30, 99)],
                channel_include={"00.17 All unfoldingWord"},
                channel_exclude={
                    "00.16 Prayer Requests",
                    "00.18 General",
                    "00.19 Family",
                    "00.20 Random",
                    "00.21 Encouragement",
                },
                exclude_non_jd=True,
                exclude_dms=True,
                exclude_private=True,
            )
        )

    def test_work_channels_allowed(self, uw_filter):
        assert uw_filter.is_channel_allowed("30 Infrastructure") is True
        assert uw_filter.is_channel_allowed("84 BT Servant") is True
        assert uw_filter.is_channel_allowed("42 Comms & Public Relations") is True
        assert uw_filter.is_channel_allowed("01 Knowledge base") is True
        assert uw_filter.is_channel_allowed("02 Cohorts") is True
        assert uw_filter.is_channel_allowed("14 Office & Facilities") is True

    def test_sensitive_channels_blocked(self, uw_filter):
        assert uw_filter.is_channel_allowed("00.16 Prayer Requests") is False
        assert uw_filter.is_channel_allowed("00.18 General") is False
        assert uw_filter.is_channel_allowed("00.19 Family") is False
        assert uw_filter.is_channel_allowed("00.20 Random") is False
        assert uw_filter.is_channel_allowed("00.21 Encouragement") is False

    def test_explicit_include_from_sensitive_area(self, uw_filter):
        assert uw_filter.is_channel_allowed("00.17 All unfoldingWord") is True

    def test_non_jd_excluded(self, uw_filter):
        assert uw_filter.is_channel_allowed("Helpdesk - ST") is False
        assert uw_filter.is_channel_allowed("Catalyst Luncheon") is False

    def test_private_channels_excluded(self, uw_filter):
        stream = {"name": "09.40 - 2026 All Staff", "invite_only": True}
        assert uw_filter.is_stream_allowed(stream) is False

    def test_area_00_without_explicit_include_blocked(self, uw_filter):
        # Area 00 is not in jd_allow_areas, so unless explicitly included, blocked
        assert uw_filter.is_channel_allowed("00.22 Some New Channel") is False


# --- Stream ID enforcement tests (P0 fix) ---


class TestStreamIdEnforcement:
    """Tests for stream ID-based access control via stream metadata index."""

    @pytest.fixture
    def filter_with_index(self):
        cf = ChannelFilter(
            ChannelFilterConfig(
                enabled=True,
                jd_allow_areas=[(30, 99)],
                channel_exclude={"00.16 Prayer Requests"},
                exclude_private=True,
            )
        )
        # Populate index as if get_streams returned these
        cf.update_stream_index([
            {"stream_id": 1, "name": "30 Infrastructure", "invite_only": False},
            {"stream_id": 2, "name": "00.16 Prayer Requests", "invite_only": False},
            {"stream_id": 3, "name": "09.40 - 2026 All Staff", "invite_only": True},
            {"stream_id": 4, "name": "84 BT Servant", "invite_only": False},
            {"stream_id": 5, "name": "Helpdesk - ST", "invite_only": False},
        ])
        return cf

    def test_allowed_stream_by_id(self, filter_with_index):
        assert filter_with_index.is_stream_id_allowed(1) is True  # 30 Infrastructure
        assert filter_with_index.is_stream_id_allowed(4) is True  # 84 BT Servant

    def test_blocked_stream_by_id_name_filter(self, filter_with_index):
        assert filter_with_index.is_stream_id_allowed(2) is False  # 00.16 Prayer Requests

    def test_blocked_stream_by_id_private(self, filter_with_index):
        assert filter_with_index.is_stream_id_allowed(3) is False  # private channel

    def test_blocked_stream_by_id_non_jd(self, filter_with_index):
        assert filter_with_index.is_stream_id_allowed(5) is False  # Helpdesk - ST

    def test_unknown_stream_id_allowed_by_default(self, filter_with_index):
        # Default: unknown IDs allowed (fail-open) for compatibility
        assert filter_with_index.is_stream_id_allowed(999) is True

    def test_unknown_stream_id_denied_when_configured(self):
        cf = ChannelFilter(
            ChannelFilterConfig(
                enabled=True,
                jd_allow_areas=[(30, 99)],
                deny_unknown_stream_ids=True,
            )
        )
        cf.update_stream_index([
            {"stream_id": 1, "name": "30 Infrastructure", "invite_only": False},
        ])
        assert cf.is_stream_id_allowed(1) is True
        assert cf.is_stream_id_allowed(999) is False

    def test_index_update_idempotent(self, filter_with_index):
        # Updating index again should not break anything
        filter_with_index.update_stream_index([
            {"stream_id": 1, "name": "30 Infrastructure", "invite_only": False},
        ])
        assert filter_with_index.is_stream_id_allowed(1) is True


# --- Privacy-aware name check (P0 fix) ---


class TestPrivacyAwareNameCheck:
    """Tests for is_channel_allowed_with_privacy()."""

    def test_private_stream_blocked_by_name_lookup(self):
        cf = ChannelFilter(
            ChannelFilterConfig(
                enabled=True,
                jd_allow_areas=[(0, 99)],
                exclude_private=True,
            )
        )
        cf.update_stream_index([
            {"stream_id": 10, "name": "09.40 - 2026 All Staff", "invite_only": True},
            {"stream_id": 11, "name": "30 Infrastructure", "invite_only": False},
        ])
        # Name passes JD filter but is private — should be blocked
        assert cf.is_channel_allowed_with_privacy("09.40 - 2026 All Staff") is False
        assert cf.is_channel_allowed_with_privacy("30 Infrastructure") is True

    def test_falls_back_when_not_in_index(self):
        cf = ChannelFilter(
            ChannelFilterConfig(
                enabled=True,
                jd_allow_areas=[(30, 99)],
                exclude_private=True,
            )
        )
        # No index populated — falls back to name-only check
        assert cf.is_channel_allowed_with_privacy("30 Infrastructure") is True
        assert cf.is_channel_allowed_with_privacy("01 Knowledge base") is False


# --- Env parsing error handling (P1 fix) ---


class TestEnvParsingErrors:
    def test_malformed_range_raises_valueerror(self):
        with pytest.raises(ValueError, match="Invalid JD area range"):
            parse_area_ranges("abc")

    def test_partially_malformed_range_raises(self):
        with pytest.raises(ValueError, match="Invalid JD area range"):
            parse_area_ranges("30-99,abc,42")

    def test_empty_range_element_ok(self):
        # Trailing comma should not crash
        assert parse_area_ranges("30-99,") == [(30, 99)]

    def test_dash_in_non_numeric_raises(self):
        with pytest.raises(ValueError, match="Invalid JD area range"):
            parse_area_ranges("ab-cd")


# --- Blocked-by-policy counters (observability) ---


class TestBlockedCounters:
    def test_counters_exist(self):
        counts = get_blocked_counts()
        assert "send" in counts
        assert "read" in counts
        assert "stream_id" in counts

    def test_filter_messages_increments_read_counter(self):
        cf = ChannelFilter(
            ChannelFilterConfig(
                enabled=True,
                jd_allow_areas=[(30, 99)],
                exclude_dms=True,
            )
        )
        before = get_blocked_counts()["read"]
        cf.filter_messages([
            {"type": "private", "display_recipient": [{"email": "a@b.com"}], "content": "dm"},
            {"type": "stream", "display_recipient": "01 Knowledge base", "content": "x"},
        ])
        after = get_blocked_counts()["read"]
        # Both DM and out-of-range stream should increment
        assert after > before
