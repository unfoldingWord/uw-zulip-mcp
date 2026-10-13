"""Unit tests for NarrowHelper utilities to improve coverage.

Covers basic builders, time filters, conversion helpers, validation,
description, and convenience wrappers.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from zulipchat_mcp.utils.narrow_helpers import (
    NarrowHelper,
    _hash_util_encode,
    build_basic_narrow,
    message_permalink,
    simple_narrow,
)

SITE = "https://chat.example.com"


def test_basic_builders_and_to_from_dict() -> None:
    nf = [
        NarrowHelper.stream("general"),
        NarrowHelper.topic("deploy"),
        NarrowHelper.sender("user@example.com"),
        NarrowHelper.search_text("bug"),
        NarrowHelper.has_attachment(),
        NarrowHelper.has_link(),
        NarrowHelper.has_image(),
        NarrowHelper.is_private(),
        NarrowHelper.is_starred(),
        NarrowHelper.is_mentioned(),
    ]
    assert NarrowHelper.validate_narrow_filters(nf)

    api = NarrowHelper.to_api_format(nf)
    back = NarrowHelper.from_dict_list(api)
    assert len(api) == len(back) == len(nf)

    desc = NarrowHelper.describe_narrow(nf[:3])
    assert "stream:general" in desc and "topic:deploy" in desc


def test_time_filters_and_ranges() -> None:
    now = datetime.now()
    nf_after = NarrowHelper.after_time(now)
    nf_before = NarrowHelper.before_time(now.isoformat())
    assert "after:" in nf_after.operand and "before:" in nf_before.operand

    last_h = NarrowHelper.last_hours(2)
    last_d = NarrowHelper.last_days(1)
    assert last_h.operator == last_d.operator

    rng = NarrowHelper.time_range(now - timedelta(days=1), now)
    assert len(rng) == 2


def test_build_basic_narrow_and_helpers() -> None:
    # Basic combination
    filters = build_basic_narrow(stream="dev", topic="t1", text="fix")
    assert any(f.operator.value == "stream" for f in filters)
    assert any(f.operator.value == "topic" for f in filters)
    assert any(f.operator.value == "search" for f in filters)

    # Combine narrows
    combined = NarrowHelper.combine_narrows(filters, [NarrowHelper.is_starred()])
    assert len(combined) == len(filters) + 1

    # Simple narrow returns API dicts
    simple = simple_narrow(stream="dev", text="deploy")
    assert isinstance(simple, list) and all("operator" in d for d in simple)


class TestHashUtilEncode:
    """Zulip's non-standard hash-fragment encoding (quote, .->%2E, %->.)."""

    def test_space_becomes_dot20(self):
        assert _hash_util_encode("test topic") == "test.20topic"

    def test_literal_dot_becomes_dot2e(self):
        assert _hash_util_encode("v0.9.0") == "v0.2E9.2E0"

    def test_ampersand_and_slash(self):
        assert _hash_util_encode("a & b/c") == "a.20.26.20b.2Fc"

    def test_non_ascii_utf8(self):
        # café -> UTF-8 %C3%A9 -> .C3.A9
        assert _hash_util_encode("café") == "caf.C3.A9"

    def test_unreserved_unchanged(self):
        assert _hash_util_encode("a-b_c~d") == "a-b_c~d"


class TestMessagePermalink:
    """Permalinks only for stream messages; None otherwise."""

    def _stream_msg(self, **over):
        msg = {
            "id": 100,
            "type": "stream",
            "stream_id": 5,
            "display_recipient": "general",
            "subject": "test topic",
        }
        msg.update(over)
        return msg

    def test_basic_stream_link(self):
        link = message_permalink(SITE, self._stream_msg())
        assert link == (f"{SITE}/#narrow/channel/5-general/topic/test.20topic/near/100")

    def test_topic_special_chars_encoded(self):
        link = message_permalink(SITE, self._stream_msg(subject="deploys & stuff"))
        assert link.endswith("/topic/deploys.20.26.20stuff/near/100")

    def test_stream_name_spaces_become_hyphens(self):
        link = message_permalink(
            SITE, self._stream_msg(stream_id=14, display_recipient="14 Dev Chat")
        )
        assert "/channel/14-14-Dev-Chat/" in link

    def test_topic_fallback_key(self):
        # Some payloads use "topic" instead of "subject".
        msg = self._stream_msg()
        del msg["subject"]
        msg["topic"] = "hello world"
        link = message_permalink(SITE, msg)
        assert link.endswith("/topic/hello.20world/near/100")

    def test_trailing_slash_in_base(self):
        link = message_permalink(SITE + "/", self._stream_msg())
        assert link == (f"{SITE}/#narrow/channel/5-general/topic/test.20topic/near/100")

    def test_missing_stream_name_falls_back_to_id(self):
        msg = self._stream_msg()
        del msg["display_recipient"]
        link = message_permalink(SITE, msg)
        assert "/channel/5-5/" in link

    def test_dm_returns_none(self):
        msg = {
            "id": 101,
            "type": "private",
            "display_recipient": [{"id": 3}, {"id": 9}],
        }
        assert message_permalink(SITE, msg) is None

    def test_dot_in_stream_name_and_quotes_in_topic(self):
        # Regression: a stream name with a literal '.' must encode to '.2E' in
        # the slug, and a single quote in the topic to '.27' — not left raw.
        # (A naive encoder leaves '.' and "'" unencoded, producing broken links.)
        msg = {
            "id": 999001,
            "type": "stream",
            "stream_id": 42,
            "display_recipient": "07 Example.Channel",
            "subject": "MCP 'Standard'",
        }
        link = message_permalink("https://chat.example.com", msg)
        assert link == (
            "https://chat.example.com/#narrow/channel/42-07-Example.2EChannel"
            "/topic/MCP.20.27Standard.27/near/999001"
        )

    def test_missing_fields_return_none(self):
        assert message_permalink("", self._stream_msg()) is None
        assert (
            message_permalink(SITE, {"type": "stream", "stream_id": 5}) is None
        )  # no id
        assert (
            message_permalink(SITE, self._stream_msg(subject=None, topic=None)) is None
        )
        no_sid = self._stream_msg()
        del no_sid["stream_id"]
        assert message_permalink(SITE, no_sid) is None
