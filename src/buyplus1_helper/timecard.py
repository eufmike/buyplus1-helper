"""Build, merge, and persist the master timecard DataFrame."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from .models import TimecardEntry

_COLUMNS = [
    "date",
    "weekday",
    "session",
    "online_time",
    "offline_time",
    "duration_hours",
    "source_file",
    "notes",
]


def build_dataframe(entries: list[TimecardEntry]) -> pd.DataFrame:
    """Convert a list of TimecardEntry objects to a DataFrame."""
    rows = []
    for e in entries:
        rows.append(
            {
                "date": e.date.isoformat(),
                "weekday": e.weekday,
                "session": e.session,
                "online_time": e.online_time.strftime("%H:%M") if e.online_time else "",
                "offline_time": e.offline_time.strftime("%H:%M") if e.offline_time else "",
                "duration_hours": e.duration_hours if e.duration_hours is not None else "",
                "source_file": e.source_file,
                "notes": e.notes,
            }
        )
    return pd.DataFrame(rows, columns=_COLUMNS)


def load_master(path: Path) -> pd.DataFrame:
    """Load the master CSV, or return an empty DataFrame if it doesn't exist."""
    if not path.exists():
        return pd.DataFrame(columns=_COLUMNS)
    return pd.read_csv(path, encoding="utf-8-sig", dtype=str).fillna("")


def merge(new: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    """
    Merge new records into master.

    Key: (date, session). If the same key exists in both, the new record wins.
    Records from master whose keys are not in new are preserved unchanged.
    """
    if new.empty:
        return master.copy()
    if master.empty:
        return new.copy()

    # Identify new keys (normalize both to str for consistent comparison)
    new_keys = set(zip(new["date"].astype(str), new["session"].astype(str)))

    # Keep master rows whose keys are NOT overwritten by new
    mask = ~master.apply(
        lambda row: (str(row["date"]), str(row["session"])) in new_keys, axis=1
    )
    preserved = master[mask]

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
