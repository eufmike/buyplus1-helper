"""Extract 曉寒's online/offline sessions from parsed chat messages."""
from __future__ import annotations

from datetime import date, timedelta
from itertools import groupby
from typing import Optional

from .models import ChatMessage, TimecardEntry

TARGET_SENDER = "曉寒"

# Phrases that indicate a conditional/future online intention — not an actual login
_ONLINE_EXCLUSIONS = (
    "有空會再上線",
    "有再上線的話",
)

# The typo 上限 is treated as 上線 when the sender is 曉寒
_ONLINE_TYPO = "上限"


def _is_online(msg: ChatMessage) -> bool:
    if msg.sender != TARGET_SENDER:
        return False
    content = msg.content
    # Treat typo as online
    if _ONLINE_TYPO in content and "下" not in content:
        return True
    if "上線" not in content:
        return False
    # Exclude conditional/future phrases
    for excl in _ONLINE_EXCLUSIONS:
        if excl in content:
            return False
    return True


def _is_offline(msg: ChatMessage) -> bool:
    return msg.sender == TARGET_SENDER and "下線" in msg.content


def extract_sessions(
    messages: list[ChatMessage], source_file: str = ""
) -> list[TimecardEntry]:
    """
    Extract online/offline sessions for 曉寒 from a list of ChatMessage objects.

    Sessions are paired greedily left-to-right within each calendar day.
    An unpaired online event produces a row with offline_time=None.
    """
    entries: list[TimecardEntry] = []

    # Group messages by date
    sorted_msgs = sorted(messages, key=lambda m: (m.date, m.timestamp or date.min))
    for day, day_msgs in groupby(sorted_msgs, key=lambda m: m.date):
        day_list = list(day_msgs)
        weekday = day_list[0].weekday

        # Collect events in order
        events: list[tuple[str, ChatMessage]] = []
        for msg in day_list:
            if _is_online(msg):
                events.append(("online", msg))
            elif _is_offline(msg):
                events.append(("offline", msg))

        # Pair greedily: online → offline → online → offline …
        session_num = 0
        i = 0
        while i < len(events):
            kind, msg = events[i]
            if kind == "online":
                session_num += 1
                online_msg = msg
                offline_msg: Optional[ChatMessage] = None
                # Look for the next offline
                if i + 1 < len(events) and events[i + 1][0] == "offline":
                    offline_msg = events[i + 1][1]
                    i += 2
                else:
                    i += 1

                online_t = online_msg.timestamp
                offline_t = offline_msg.timestamp if offline_msg else None

                duration: Optional[float] = None
                if online_t and offline_t:
                    delta = timedelta(
                        hours=offline_t.hour - online_t.hour,
                        minutes=offline_t.minute - online_t.minute,
                    )
                    duration = round(delta.total_seconds() / 3600, 2)

                entries.append(
                    TimecardEntry(
                        date=day,
                        weekday=weekday,
                        session=session_num,
                        online_time=online_t,
                        offline_time=offline_t,
                        duration_hours=duration,
                        source_file=source_file,
                        notes=offline_msg.content if offline_msg else "",
                    )
                )
            else:
                # Stray offline without a preceding online — skip
                i += 1

    return entries
