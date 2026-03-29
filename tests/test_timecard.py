"""Tests for the timecard DataFrame builder and merge logic."""
from datetime import date, time
from pathlib import Path

import pandas as pd
import pytest

from buyplus1_helper.models import TimecardEntry
from buyplus1_helper.timecard import build_dataframe, load_master, merge, save_master


def _entry(d: date, session: int, on: time, off: time, src: str = "test.txt") -> TimecardEntry:
    delta_minutes = (off.hour - on.hour) * 60 + (off.minute - on.minute)
    return TimecardEntry(
        date=d,
        weekday="Thursday",
        session=session,
        online_time=on,
        offline_time=off,
        duration_hours=round(delta_minutes / 60, 2),
        source_file=src,
        notes="我先下線",
    )


# Entries use Taiwan Time (UTC+8) directly — the LLM extractor performs the
# PT→TW conversion before creating TimecardEntry objects.
#
# Original PT times for reference (2023-09-07 / 2023-09-10 are both PDT, UTC-7):
#   PT 17:08 on Sep 7  → TW 08:08 on Sep 8   (+15h PDT→TW)
#   PT 20:30 on Sep 7  → TW 11:30 on Sep 8
#   PT 22:01 on Sep 7  → TW 13:01 on Sep 8
#   PT 23:35 on Sep 7  → TW 14:35 on Sep 8
#   PT 16:53 on Sep 10 → TW 07:53 on Sep 11
#   PT 22:04 on Sep 10 → TW 13:04 on Sep 11
E1 = _entry(date(2023, 9, 8), 1, time(8, 8),  time(11, 30))
E2 = _entry(date(2023, 9, 8), 2, time(13, 1), time(14, 35))
E3 = _entry(date(2023, 9, 11), 1, time(7, 53), time(13, 4))


def test_build_dataframe_shape():
    df = build_dataframe([E1, E2, E3])
    assert df.shape == (3, 13)


def test_build_dataframe_columns():
    df = build_dataframe([E1])
    assert list(df.columns) == [
        "date", "weekday", "session",
        "online_time", "offline_time",
        "online_time_tw", "offline_time_tw",
        "online_time_gmt", "offline_time_gmt",
        "duration_hours", "temp_leave_minutes",
        "source_file", "notes",
    ]


def test_build_dataframe_values():
    df = build_dataframe([E1])
    row = df.iloc[0]
    assert row["date"] == "2023-09-08"
    # online_time and online_time_tw are both TW (same value)
    assert row["online_time"] == "08:08"
    assert row["online_time_tw"] == "08:08"
    assert row["offline_time"] == "11:30"
    assert row["offline_time_tw"] == "11:30"
    # GMT = TW - 8h (no DST needed, TW is fixed UTC+8)
    assert row["online_time_gmt"] == "00:08"
    assert row["offline_time_gmt"] == "03:30"


def test_load_master_missing_returns_empty(tmp_path):
    df = load_master(tmp_path / "nonexistent.csv")
    assert df.empty


def test_save_and_load_roundtrip(tmp_path):
    df = build_dataframe([E1, E2])
    path = tmp_path / "master.csv"
    save_master(df, path)
    loaded = load_master(path)
    assert list(loaded["date"]) == ["2023-09-08", "2023-09-08"]
    assert list(loaded["session"]) == ["1", "2"]


def test_merge_new_into_empty():
    new = build_dataframe([E1])
    master = pd.DataFrame(columns=new.columns)
    result = merge(new, master)
    assert len(result) == 1


def test_merge_preserves_existing():
    master = build_dataframe([E1])
    new = build_dataframe([E3])
    result = merge(new, master)
    assert len(result) == 2


def test_merge_overwrites_same_key():
    master = build_dataframe([E1])  # session 1 on Sep 8 TW
    new_entry = _entry(date(2023, 9, 8), 1, time(8, 0), time(13, 0), src="new.txt")
    new = build_dataframe([new_entry])
    result = merge(new, master)
    assert len(result) == 1
    assert result.iloc[0]["online_time"] == "08:00"
    assert result.iloc[0]["source_file"] == "new.txt"


def test_merge_sorted_by_date_session():
    master = build_dataframe([E3])
    new = build_dataframe([E1, E2])
    result = merge(new, master)
    assert list(result["date"]) == ["2023-09-08", "2023-09-08", "2023-09-11"]
