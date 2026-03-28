"""Build, merge, and persist the master timecard DataFrame."""
from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
from pathlib import Path

import pandas as pd

from .models import TimecardEntry

_COLUMNS = [
    "date",
    "weekday",
    "session",
    "online_time",         # Pacific Time (raw)
    "offline_time",        # Pacific Time (raw)
    "online_time_tw",      # Taiwan UTC+8
    "offline_time_tw",     # Taiwan UTC+8
    "online_time_gmt",     # GMT/UTC
    "offline_time_gmt",    # GMT/UTC
    "duration_hours",      # net working hours (excl. temp leave)
    "temp_leave_minutes",  # total temp leave duration
    "source_file",
    "notes",
]

# US Pacific DST schedule (second Sunday of March → first Sunday of November).
# LINE exports use the device's local clock — this repo's device is in Pacific time.
def _pt_utc_offset(d: date) -> int:
    """Return UTC offset in hours for Pacific time on the given date.
    PDT (UTC-7) applies from the second Sunday of March through the first
    Sunday of November; PST (UTC-8) applies otherwise.
    """
    year = d.year
    # Second Sunday of March (DST start)
    mar1 = date(year, 3, 1)
    first_sun_mar = mar1 + timedelta(days=(6 - mar1.weekday()) % 7)
    dst_start = first_sun_mar + timedelta(weeks=1)
    # First Sunday of November (DST end)
    nov1 = date(year, 11, 1)
    dst_end = nov1 + timedelta(days=(6 - nov1.weekday()) % 7)
    if dst_start <= d < dst_end:
        return -7   # PDT
    return -8       # PST


def _pt_to_utc_offset(time_str: str, d: date, target_offset: int) -> str:
    """Convert a 'HH:MM' Pacific time string to another UTC offset.

    target_offset: hours east of UTC (e.g. 0 for GMT, 8 for Taiwan).
    Returns '' if time_str is empty/NaN. Wraps within 24 hours.
    """
    if not time_str or pd.isna(time_str):
        return ""
    try:
        h, m = map(int, str(time_str).split(":"))
    except ValueError:
        return ""
    pt_offset = _pt_utc_offset(d)          # e.g., -7 for PDT
    total_minutes = (h * 60 + m) - (pt_offset * 60) + (target_offset * 60)
    total_minutes %= 24 * 60
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def _pt_to_gmt(time_str: str, d: date) -> str:
    return _pt_to_utc_offset(time_str, d, target_offset=0)


def _pt_to_tw(time_str: str, d: date) -> str:
    """Convert 'HH:MM' Pacific time to Taiwan time (UTC+8, no DST)."""
    return _pt_to_utc_offset(time_str, d, target_offset=8)


def build_dataframe(entries: list[TimecardEntry]) -> pd.DataFrame:
    """Convert a list of TimecardEntry objects to a DataFrame.

    Timestamps in the source data are Pacific time (device local clock).
    online_time_gmt / offline_time_gmt are the UTC equivalents, accounting
    for PDT (UTC-7) and PST (UTC-8) transitions.
    """
    rows = []
    for e in entries:
        online_str  = e.online_time.strftime("%H:%M")  if e.online_time  else ""
        offline_str = e.offline_time.strftime("%H:%M") if e.offline_time else ""
        rows.append(
            {
                "date": e.date.isoformat(),
                "weekday": e.weekday,
                "session": e.session,
                "online_time":      online_str,
                "offline_time":     offline_str,
                "online_time_tw":   _pt_to_tw(online_str,  e.date),
                "offline_time_tw":  _pt_to_tw(offline_str, e.date),
                "online_time_gmt":  _pt_to_gmt(online_str,  e.date),
                "offline_time_gmt": _pt_to_gmt(offline_str, e.date),
                "duration_hours": e.duration_hours if e.duration_hours is not None else "",
                "temp_leave_minutes": e.temp_leave_minutes if e.temp_leave_minutes is not None else "",
                "source_file": e.source_file,
                "notes": e.notes,
            }
        )
    return pd.DataFrame(rows, columns=_COLUMNS)


def load_master(path: Path) -> pd.DataFrame:
    """Load the master CSV, or return an empty DataFrame if it doesn't exist."""
    if not path.exists():
        return pd.DataFrame(columns=_COLUMNS)
    df = pd.read_csv(path, encoding="utf-8-sig", dtype=str).fillna("")
    # Back-fill columns added after initial release
    for col in ("online_time_tw", "offline_time_tw", "online_time_gmt", "offline_time_gmt", "temp_leave_minutes"):
        if col not in df.columns:
            df[col] = ""
    return df[_COLUMNS]


def merge(new: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    """
    Merge new records into master.

    Key: date. All existing master rows for any date present in new are
    replaced entirely by the new rows for that date.  This ensures that
    if the extractor now produces fewer sessions per day (e.g., one
    instead of three), stale extra sessions don't linger in the master.
    """
    if new.empty:
        return master.copy()
    if master.empty:
        return new.copy()

    # Drop all master rows for dates that are being re-processed
    new_dates = set(new["date"].astype(str))
    preserved = master[~master["date"].astype(str).isin(new_dates)]

    merged = pd.concat([preserved, new], ignore_index=True)
    merged = merged.sort_values(["date", "session"]).reset_index(drop=True)
    return merged


def save_master(df: pd.DataFrame, path: Path) -> None:
    """Write the master DataFrame to a UTF-8-BOM CSV (Excel-compatible)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def export_excel(df: pd.DataFrame, path: Path) -> None:
    """Export the DataFrame to an Excel file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(path, index=False, engine="openpyxl")
