"""Extract 曉寒's online/offline sessions from parsed chat messages."""
from __future__ import annotations

from datetime import date, timedelta
from itertools import groupby
from typing import TYPE_CHECKING, Optional

from .models import ChatMessage, TimecardEntry

if TYPE_CHECKING:
    from .llm_validator import LLMValidator

TARGET_SENDER = "曉寒"

# Exact short messages that are confirmed typos for 上線
_ONLINE_TYPO_EXACT: frozenset[str] = frozenset({"上限", "我上限"})

# Messages starting with these are unambiguous current login announcements —
# skip exclusion checks entirely.
_ONLINE_ANCHORS: tuple[str, ...] = (
    "上線",
    "我上線",
    "回來上線",
    "先上線",
    "我先上線",
    "我回來上線",
)

# Phrases indicating a future/conditional/inability-to-go-online intent.
# Checked only when no anchor is present at the start of the message.
_ONLINE_EXCLUSIONS: tuple[str, ...] = (
    "有空會再上線",
    "有再上線的話",
    "晚一點上線",
    "晚點上線",
    "才能上線",
    "才會上線",
    "沒辦法上線",
    "等等上線",
    "等等會上線",
    "等等再回來上線",
)

# Patterns that pass keyword rules but are inherently ambiguous — require LLM.
# Example: 「我10分鐘後上線」 「大概三個小時後上線喔」
_AMBIGUOUS_PATTERNS: tuple[str, ...] = ("後上線",)


def _is_online(msg: ChatMessage) -> bool:
    """Return True if the message is a definitive current login (no LLM needed)."""
    if msg.sender != TARGET_SENDER:
        return False
    content = msg.content.strip()

    # Exact typo match (short message only — avoids false positives like "金額上限")
    if content in _ONLINE_TYPO_EXACT:
        return True

    if "上線" not in content:
        return False

    # Unambiguous login announcement at the start — always valid
    for anchor in _ONLINE_ANCHORS:
        if content.startswith(anchor):
            return True

    # No anchor — check for future/conditional exclusion phrases
    for excl in _ONLINE_EXCLUSIONS:
        if excl in content:
            return False

    # Ambiguous patterns should not be auto-accepted; defer to LLM
    for pat in _AMBIGUOUS_PATTERNS:
        if pat in content:
            return False

    return True


def _is_ambiguous_online(msg: ChatMessage) -> bool:
    """Return True if the message needs LLM classification (deferred login intent)."""
    if msg.sender != TARGET_SENDER:
        return False
    content = msg.content.strip()
    if content in _ONLINE_TYPO_EXACT:
        return False
    if "上線" not in content:
        return False
    # Already handled as definitive online or exclusion
    for anchor in _ONLINE_ANCHORS:
        if content.startswith(anchor):
            return False
    for excl in _ONLINE_EXCLUSIONS:
        if excl in content:
            return False
    return any(pat in content for pat in _AMBIGUOUS_PATTERNS)


# Substrings whose presence (in 曉寒's message) marks a departure.
# Order matters for readability; all are checked with `in`.
_OFFLINE_KEYWORDS: tuple[str, ...] = (
    "下線",     # canonical: 先下線, 我先下線, 下線囉, …
    "離線",     # alternative: 先離線一下, 我先離線, …
    "離開",     # common in 2024–2026: 我先離開一下, 先離開, …
    "先下",     # short form: 我先下, 先下喔, 先下囉, 先下一下, …
    "下囉",     # sentence-final: 好啦～那我下囉, 先下囉, …
    "下喔",     # sentence-final with 喔: 先下喔, …
    "去接小孩", # specific activity: 我先去接小孩, …
    "先來嚇了", # typo for 先來下了 (autocorrect artefact)
)

# Substrings that cancel an otherwise-matched offline keyword.
# E.g. 來下載 contains 來下 but is a download, not a logout.
_OFFLINE_EXCLUSIONS: tuple[str, ...] = (
    "來下載",   # download
    "先下午",   # 先下午…
)


def _is_offline(msg: ChatMessage) -> bool:
    if msg.sender != TARGET_SENDER:
        return False
    content = msg.content
    for excl in _OFFLINE_EXCLUSIONS:
        if excl in content:
            return False
    return any(kw in content for kw in _OFFLINE_KEYWORDS)


def extract_sessions(
    messages: list[ChatMessage],
    source_file: str = "",
    llm_validator: Optional["LLMValidator"] = None,
) -> list[TimecardEntry]:
    """
    Extract online/offline sessions for 曉寒 from a list of ChatMessage objects.

    Sessions are paired greedily left-to-right within each calendar day.
    An unpaired online event produces a row with offline_time=None.

    Args:
        messages: Parsed chat messages.
        source_file: Name of the source file (stored in each entry).
        llm_validator: Optional LLMValidator for ambiguous 後上線 messages.
                       When None, ambiguous messages are skipped.
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
            elif llm_validator and _is_ambiguous_online(msg):
                if llm_validator.is_online_now(msg.content):
                    events.append(("online", msg))

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
