"""Pydantic models for chat parsing and timecard output."""
from __future__ import annotations

from datetime import date, time
from typing import Optional

from pydantic import BaseModel


class ChatMessage(BaseModel):
    """A single parsed message from the chat history."""

    date: date
    weekday: str
    timestamp: Optional[time] = None
    sender: Optional[str] = None
    content: str


class TimecardEntry(BaseModel):
    """One online→offline session for 曉寒."""

    date: date
    weekday: str
    session: int
    online_time: Optional[time] = None
    offline_time: Optional[time] = None
    duration_hours: Optional[float] = None
    temp_leave_minutes: Optional[float] = None
    source_file: str
    notes: str = ""
