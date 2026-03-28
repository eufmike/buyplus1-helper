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


E1 = _entry(date(2023, 9, 7), 1, time(17, 8), time(20, 30))
E2 = _entry(date(2023, 9, 7), 2, time(22, 1), time(23, 35))
E3 = _entry(date(2023, 9, 10), 1, time(16, 53), time(22, 4))


def test_build_dataframe_shape():
    df = build_dataframe([E1, E2, E3])
    assert df.shape == (3, 10)


def test_build_dataframe_columns():
    df = build_dataframe([E1])
    assert list(df.columns) == [
        "date", "weekday", "session", "online_time",
        "offline_time", "online_time_gmt", "offline_time_gmt",
        "duration_hours", "source_file", "notes",
    ]


def test_build_dataframe_values():
    df = build_dataframe([E1])
    row = df.iloc[0]
    assert row["date"] == "2023-09-07"
    assert row["online_time"] == "17:08"
    assert row["offline_time"] == "20:30"
    # 2023-09-07 is PDT (UTC-7); 17:08 PT + 7h = 00:08 UTC (next day, wraps mod 24)
    assert row["online_time_gmt"] == "00:08"
    # 20:30 PT + 7h = 03:30 UTC
    assert row["offline_time_gmt"] == "03:30"


def test_load_master_missing_returns_empty(tmp_path):
    df = load_master(tmp_path / "nonexistent.csv")
    assert df.empty


def test_save_and_load_roundtrip(tmp_path):
    df = build_dataframe([E1, E2])
    path = tmp_path / "master.csv"
    save_master(df, path)
    loaded = load_master(path)
    assert list(loaded["date"]) == ["2023-09-07", "2023-09-07"]
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
    master = build_dataframe([E1])  # session 1 on Sep 7
    new_entry = _entry(date(2023, 9, 7), 1, time(17, 0), time(21, 0), src="new.txt")
    new = build_dataframe([new_entry])
    result = merge(new, master)
    assert len(result) == 1
    assert result.iloc[0]["online_time"] == "17:00"
    assert result.iloc[0]["source_file"] == "new.txt"


def test_merge_sorted_by_date_session():
    master = build_dataframe([E3])
    new = build_dataframe([E1, E2])
    result = merge(new, master)
    assert list(result["date"]) == ["2023-09-07", "2023-09-07", "2023-09-10"]
