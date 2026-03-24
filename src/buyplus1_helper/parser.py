"""Parse LINE-style chat history exports into ChatMessage objects."""
from __future__ import annotations

import re
from datetime import date, time
from pathlib import Path
from typing import Optional

from .models import ChatMessage

# 2023.09.07 Thursday
_DATE_HEADER = re.compile(r"^(\d{4})\.(\d{2})\.(\d{2})\s+(\w+)$")

# 17:08 曉寒 我上線
# Sender may contain emoji and spaces; we capture up to the second whitespace group.
# Strategy: split on first occurrence of "HH:MM ", then split remainder on first " "
_MSG_LINE = re.compile(r"^(\d{2}):(\d{2})\s+(.*)$")


def _parse_time(h: str, m: str) -> time:
    return time(int(h), int(m))


def parse_file(path: Path) -> list[ChatMessage]:
    """Read a chat history file and return all parsed ChatMessage objects."""
    text = path.read_text(encoding="utf-8", errors="replace")
    return parse_text(text, source_name=path.name)


def parse_text(text: str, source_name: str = "") -> list[ChatMessage]:
    """Parse raw chat text into a list of ChatMessage objects."""
    messages: list[ChatMessage] = []
    current_date: Optional[date] = None
    current_weekday: str = ""

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Check for date header
        date_match = _DATE_HEADER.match(line)
        if date_match:
            y, mo, d, wd = date_match.groups()
            current_date = date(int(y), int(mo), int(d))
            current_weekday = wd
            continue

        if current_date is None:
            # Haven't seen a date header yet — skip
            continue

        # Check for a timestamped message
        msg_match = _MSG_LINE.match(line)
        if msg_match:
            h, m, rest = msg_match.groups()
            msg_time = _parse_time(h, m)
            # Split sender from content on first whitespace run
            parts = rest.split(None, 1)
            sender: Optional[str] = None
            content = rest
            if len(parts) == 2:
                sender, content = parts
            elif len(parts) == 1:
                sender = parts[0]
                content = ""
            messages.append(
                ChatMessage(
                    date=current_date,
                    weekday=current_weekday,
                    timestamp=msg_time,
                    sender=sender,
                    content=content,
                )
            )
        # Continuation lines (no timestamp) are intentionally skipped

    return messages
