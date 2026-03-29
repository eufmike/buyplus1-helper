"""Tests for the LLM-based session extractor (unit tests, no API calls)."""
from datetime import date, time, timedelta
from typing import Optional

import pytest

from buyplus1_helper.llm_extractor import (
    _format_batch,
    _merge_to_one_per_day,
    _messages_to_tw,
    _parse_response,
    _split_into_daily_chunks,
)
from buyplus1_helper.models import ChatMessage, TimecardEntry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _msg(sender: str, content: str, d: date, t: time) -> ChatMessage:
    return ChatMessage(date=d, weekday="Tuesday", timestamp=t, sender=sender, content=content)


def _entry(
    d: date,
    online: Optional[time],
    offline: Optional[time],
    session: int = 1,
) -> TimecardEntry:
    duration: Optional[float] = None
    if online and offline:
        delta = timedelta(hours=offline.hour - online.hour, minutes=offline.minute - online.minute)
        duration = round(delta.total_seconds() / 3600, 2)
    return TimecardEntry(
        date=d,
        weekday="Tuesday",
        session=session,
        online_time=online,
        offline_time=offline,
        duration_hours=duration,
        source_file="test",
        notes="",
    )


D1 = date(2023, 10, 3)
D2 = date(2023, 10, 4)


# ---------------------------------------------------------------------------
# _format_batch
# ---------------------------------------------------------------------------

class TestFormatBatch:
    def test_includes_messages(self):
        msgs = [_msg("曉寒", "我上線", D1, time(17, 11))]
        text = _format_batch(msgs)
        assert "我上線" in text
        assert "17:11" in text

    def test_date_header_included(self):
        msgs = [_msg("曉寒", "我上線", D1, time(17, 11))]
        text = _format_batch(msgs)
        assert "2023-10-03" in text

    def test_no_prev_day_context_block(self):
        msgs = [_msg("曉寒", "我上線", D1, time(17, 11))]
        text = _format_batch(msgs)
        assert "[前日參考]" not in text

    def test_sorted_by_time(self):
        msgs = [
            _msg("曉寒", "我下線", D1, time(22, 0)),
            _msg("曉寒", "我上線", D1, time(17, 0)),
        ]
        text = _format_batch(msgs)
        assert text.index("17:00") < text.index("22:00")

    def test_no_context_messages_parameter(self):
        """_format_batch must not accept a context_messages parameter."""
        import inspect
        sig = inspect.signature(_format_batch)
        assert "context_messages" not in sig.parameters


# ---------------------------------------------------------------------------
# _split_into_daily_chunks
# ---------------------------------------------------------------------------

class TestSplitIntoDaily:
    def test_returns_two_tuples(self):
        msgs = [_msg("曉寒", "x", D1, time(10, 0))]
        chunks = _split_into_daily_chunks(msgs)
        assert len(chunks) == 1
        assert len(chunks[0]) == 2  # (date, messages) — no prev_msgs third element

    def test_groups_by_date(self):
        msgs = [
            _msg("曉寒", "a", D1, time(10, 0)),
            _msg("曉寒", "b", D2, time(11, 0)),
        ]
        chunks = _split_into_daily_chunks(msgs)
        assert len(chunks) == 2
        assert chunks[0][0] == D1
        assert chunks[1][0] == D2


# ---------------------------------------------------------------------------
# _merge_to_one_per_day
# ---------------------------------------------------------------------------

class TestMergeToOnePerDay:
    def test_single_entry_unchanged(self):
        e = _entry(D1, time(17, 0), time(22, 0))
        result = _merge_to_one_per_day([e])
        assert len(result) == 1
        assert result[0].online_time == time(17, 0)
        assert result[0].offline_time == time(22, 0)

    def test_session_set_to_one(self):
        e = _entry(D1, time(17, 0), time(22, 0), session=3)
        result = _merge_to_one_per_day([e])
        assert result[0].session == 1

    def test_overlapping_sessions_collapsed(self):
        """Reproduces the 2023-10-03 bug: s3 nested inside s2."""
        entries = [
            _entry(D1, time(17, 11), time(23, 30), session=2),
            _entry(D1, time(21, 56), time(23, 30), session=3),
        ]
        result = _merge_to_one_per_day(entries)
        assert len(result) == 1
        assert result[0].online_time == time(17, 11)
        assert result[0].offline_time == time(23, 30)

    def test_takes_earliest_online_and_latest_offline(self):
        entries = [
            _entry(D1, time(17, 0), time(20, 0), session=1),
            _entry(D1, time(20, 0), time(23, 0), session=2),
        ]
        result = _merge_to_one_per_day(entries)
        assert len(result) == 1
        assert result[0].online_time == time(17, 0)
        assert result[0].offline_time == time(23, 0)

    def test_null_offline_preserved_when_all_null(self):
        entries = [
            _entry(D1, time(17, 0), None),
            _entry(D1, time(21, 0), None),
        ]
        result = _merge_to_one_per_day(entries)
        assert len(result) == 1
        assert result[0].offline_time is None

    def test_non_null_offline_wins_over_null(self):
        entries = [
            _entry(D1, time(17, 0), None),
            _entry(D1, time(21, 0), time(23, 0)),
        ]
        result = _merge_to_one_per_day(entries)
        assert result[0].offline_time == time(23, 0)
        assert result[0].online_time == time(17, 0)

    def test_different_days_not_merged(self):
        entries = [
            _entry(D1, time(17, 0), time(22, 0)),
            _entry(D2, time(18, 0), time(23, 0)),
        ]
        result = _merge_to_one_per_day(entries)
        assert len(result) == 2
        assert result[0].date == D1
        assert result[1].date == D2

    def test_duration_summed_after_merge(self):
        """duration_hours = sum of individual durations (net), not total span."""
        entries = [
            _entry(D1, time(17, 0), time(20, 0)),   # 3h
            _entry(D1, time(21, 0), time(23, 0)),   # 2h
        ]
        result = _merge_to_one_per_day(entries)
        # Net working time: 3 + 2 = 5h (not the 6h span)
        assert result[0].duration_hours == 5.0
        # Temp leave: span(6h) - net(5h) = 60 min
        assert result[0].temp_leave_minutes == 60.0


# ---------------------------------------------------------------------------
# _parse_response — cross-midnight sessions
# ---------------------------------------------------------------------------

class TestParseResponseCrossMidnight:
    """Verify that cross-midnight segment arithmetic works correctly."""

    def test_cross_midnight_segment_duration(self):
        """22:06→00:34 segment should compute duration as 2h28m (148 min), not negative."""
        raw = '[{"date": "2026-02-07", "segments": [{"start": "22:06", "end": "00:34"}]}]'
        entries = _parse_response(raw, "test")
        assert len(entries) == 1
        e = entries[0]
        assert e.date == date(2026, 2, 7)
        assert e.online_time == time(22, 6)
        assert e.offline_time == time(0, 34)
        # 22:06 → 00:34 crosses midnight: 148 minutes = 2.47h
        assert e.duration_hours == round(148 / 60, 2)

    def test_cross_midnight_temp_leave_zero(self):
        """Single segment spanning midnight has zero temp_leave."""
        raw = '[{"date": "2026-02-07", "segments": [{"start": "22:06", "end": "00:34"}]}]'
        entries = _parse_response(raw, "test")
        assert entries[0].temp_leave_minutes == 0.0

    def test_cross_midnight_with_earlier_segment(self):
        """Day session + late-night cross-midnight session: duration = sum of both."""
        raw = '[{"date": "2026-02-07", "segments": [{"start": "17:00", "end": "20:00"}, {"start": "22:00", "end": "00:30"}]}]'
        entries = _parse_response(raw, "test")
        assert len(entries) == 1
        e = entries[0]
        # 17:00→20:00 = 180 min; 22:00→00:30 crosses midnight = 150 min; total = 330 min
        assert e.duration_hours == round(330 / 60, 2)


# ---------------------------------------------------------------------------
# _messages_to_tw — PT→TW conversion eliminates midnight crossings
# ---------------------------------------------------------------------------

class TestMessagesToTw:
    """_messages_to_tw converts PT dates/times to TW, removing midnight crossings."""

    def test_pst_evening_maps_to_next_tw_day(self):
        """22:06 PT (PST, Feb = UTC-8) → 14:06 TW the next calendar day."""
        # D1 = date(2023, 10, 3) is PDT; use a PST date for clarity
        pst_date = date(2026, 2, 7)   # Feb = PST (UTC-8)
        msgs = [_msg("曉寒", "上線上架", pst_date, time(22, 6))]
        tw_msgs = _messages_to_tw(msgs)
        assert tw_msgs[0].date == date(2026, 2, 8)     # next calendar day in TW
        assert tw_msgs[0].timestamp == time(14, 6)     # 22:06 + 16h = 38:06 → 14:06

    def test_pst_offline_same_tw_day(self):
        """00:34 PT (PST, Feb 8) → 16:34 TW on Feb 8 — same TW day as the online above."""
        pst_date = date(2026, 2, 8)
        msgs = [_msg("曉寒", "下線", pst_date, time(0, 34))]
        tw_msgs = _messages_to_tw(msgs)
        assert tw_msgs[0].date == date(2026, 2, 8)     # same TW day
        assert tw_msgs[0].timestamp == time(16, 34)    # 00:34 + 16h = 16:34

    def test_pdt_evening_maps_to_next_tw_day(self):
        """17:08 PT (PDT, Sep 7 = UTC-7) → 08:08 TW on Sep 8."""
        pdt_date = date(2023, 9, 7)   # Sep = PDT (UTC-7)
        msgs = [_msg("曉寒", "我上線", pdt_date, time(17, 8))]
        tw_msgs = _messages_to_tw(msgs)
        assert tw_msgs[0].date == date(2023, 9, 8)
        assert tw_msgs[0].timestamp == time(8, 8)      # 17:08 + 15h = 32:08 → 08:08

    def test_no_midnight_crossing_after_conversion(self):
        """After PT→TW, both online (22:06) and offline (00:34) land on the same TW day."""
        pst_date = date(2026, 2, 7)
        msgs = [
            _msg("曉寒", "上線上架", pst_date,                  time(22, 6)),
            _msg("曉寒", "下線",     pst_date + timedelta(days=1), time(0, 34)),
        ]
        tw_msgs = _messages_to_tw(msgs)
        assert tw_msgs[0].date == tw_msgs[1].date   # both on Feb 8 TW
        chunks = _split_into_daily_chunks(tw_msgs)
        assert len(chunks) == 1                     # one chunk, no crossing
