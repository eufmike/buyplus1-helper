"""Tests for the LLM-based session extractor (unit tests, no API calls)."""
from datetime import date, time, timedelta
from typing import Optional

import pytest

from buyplus1_helper.llm_extractor import (
    _format_batch,
    _merge_to_one_per_day,
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
