"""Tests for the chat history parser."""
from datetime import date, time
from pathlib import Path

import pytest

from buyplus1_helper.parser import parse_file, parse_text

FIXTURE = Path(__file__).parent / "fixtures" / "sample_chat.txt"


def test_parse_file_returns_messages():
    msgs = parse_file(FIXTURE)
    assert len(msgs) > 0


def test_date_and_weekday_assigned():
    msgs = parse_file(FIXTURE)
    first = msgs[0]
    assert first.date == date(2023, 9, 7)
    assert first.weekday == "Thursday"


def test_message_time_and_sender():
    msgs = parse_file(FIXTURE)
    # Second message: "17:08 曉寒 我上線"
    xh_msgs = [m for m in msgs if m.sender == "曉寒"]
    assert xh_msgs[0].timestamp == time(17, 8)
    assert "上線" in xh_msgs[0].content


def test_continuation_lines_skipped():
    text = """\
2023.09.07 Thursday
17:08 曉寒 我上線
這是一個沒有時間的延續行
18:00 ❤️Candice❤️ 好
"""
    msgs = parse_text(text)
    assert len(msgs) == 2  # continuation line not counted


def test_multiple_days():
    msgs = parse_file(FIXTURE)
    dates = {m.date for m in msgs}
    assert date(2023, 9, 7) in dates
    assert date(2023, 9, 8) in dates
    assert date(2023, 9, 10) in dates


def test_sender_with_emoji():
    msgs = parse_file(FIXTURE)
    senders = {m.sender for m in msgs}
    assert "❤️Candice❤️" in senders


def test_no_messages_before_first_date_header():
    text = "17:08 曉寒 我上線\n2023.09.07 Thursday\n17:08 曉寒 我上線\n"
    msgs = parse_text(text)
    assert len(msgs) == 1  # only the one after the date header
