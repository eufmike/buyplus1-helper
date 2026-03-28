"""Tests for the online/offline session extractor."""
from datetime import date, time
from pathlib import Path

from buyplus1_helper.extractor import _is_ambiguous_offline, _is_offline, _is_online, extract_sessions
from buyplus1_helper.models import ChatMessage
from buyplus1_helper.parser import parse_file

FIXTURE = Path(__file__).parent / "fixtures" / "sample_chat.txt"


def _msg(sender: str, content: str, d: date = date(2023, 9, 7), t: time = time(10, 0)):
    return ChatMessage(date=d, weekday="Thursday", timestamp=t, sender=sender, content=content)


# --- _is_online ---

def test_online_basic():
    assert _is_online(_msg("曉寒", "我上線"))


def test_online_return():
    assert _is_online(_msg("曉寒", "回來上線"))


def test_online_typo():
    assert _is_online(_msg("曉寒", "我上限"))


def test_online_with_purpose():
    assert _is_online(_msg("曉寒", "我上線來發匯款通知"))


def test_online_excludes_conditional():
    assert not _is_online(_msg("曉寒", "我下午有空會再上線處理"))

def test_online_excludes_future_late():
    assert not _is_online(_msg("曉寒", "我晚一點上線喔"))

def test_online_excludes_future_late2():
    assert not _is_online(_msg("曉寒", "我今天會晚點上線"))

def test_online_excludes_inability():
    assert not _is_online(_msg("曉寒", "我上午沒辦法上線"))

def test_online_excludes_future_later():
    assert not _is_online(_msg("曉寒", "等等會上線"))

def test_online_excludes_future_return():
    assert not _is_online(_msg("曉寒", "我先下，等等再回來上線"))

def test_online_typo_exact_only():
    # Long message containing 上限 in a different context is NOT a login
    assert not _is_online(_msg("曉寒", "如果是不一樣的話應該沒有上限～"))
    assert not _is_online(_msg("曉寒", "我們超商取貨不付款是不是有金額上限啊？"))

def test_online_anchor_overrides_exclusion():
    # Message starts with 先上線 (anchor) — valid even though it also mentions 晚點
    assert _is_online(_msg("曉寒", "先上線，晚上有事，會台灣時間11點後才再上線喔"))

def test_online_anchor_start():
    assert _is_online(_msg("曉寒", "上線，今天臨時有點事情，可能會晚點才上線"))


def test_online_excludes_other_sender():
    assert not _is_online(_msg("Fangtzu Chang", "曉寒妳有再上線的話 麻煩幫忙催款"))


def test_online_excludes_other_sender_mentioning_xh():
    assert not _is_online(_msg("❤️Candice❤️", "我上線"))


# --- _is_offline ---

def test_offline_basic():
    assert _is_offline(_msg("曉寒", "我先下線喔"))


def test_offline_with_reason():
    assert _is_offline(_msg("曉寒", "我先來下線接小孩"))


def test_offline_wrong_sender():
    assert not _is_offline(_msg("❤️Candice❤️", "我先下線"))


def test_offline_short_xia():
    assert _is_offline(_msg("曉寒", "我先下"))


def test_offline_short_xia_particle():
    assert _is_offline(_msg("曉寒", "先下囉"))
    assert _is_offline(_msg("曉寒", "先下喔"))


def test_offline_likai_is_ambiguous_not_definitive():
    # 離開 is ambiguous — requires LLM, not auto-classified by _is_offline
    assert not _is_offline(_msg("曉寒", "我先離開一下"))
    assert _is_ambiguous_offline(_msg("曉寒", "我先離開一下"))


def test_offline_lixian():
    assert _is_offline(_msg("曉寒", "先離線一下，等等回來"))


def test_offline_activity():
    assert _is_offline(_msg("曉寒", "我先去接小孩"))


def test_offline_xian_lai_xia():
    # 先來下 (without 線) — NOT matched by 先下 because chars are 先→來→下
    assert _is_offline(_msg("曉寒", "我先來下，等等下午再來上"))
    assert _is_offline(_msg("曉寒", "先來下～"))
    assert _is_offline(_msg("曉寒", "我先來下"))


def test_offline_typo_xia():
    assert _is_offline(_msg("曉寒", "我先來嚇了"))


def test_offline_no_download_false_positive():
    # 來下載 contains 來下 but is a download action, not going offline
    assert not _is_offline(_msg("曉寒", "我要來下載這個"))


# --- extract_sessions ---

def test_extract_sessions_count():
    msgs = parse_file(FIXTURE)
    sessions = extract_sessions(msgs, source_file="sample_chat.txt")
    # Sep 7: 2; Sep 10: 1; Sep 12: 2; Sep 13: 2 (typo 上限 + correction 上線 = 2 online events)
    assert len(sessions) == 7


def test_session_numbering():
    msgs = parse_file(FIXTURE)
    sessions = extract_sessions(msgs, source_file="sample_chat.txt")
    sep7 = [s for s in sessions if s.date == date(2023, 9, 7)]
    assert len(sep7) == 2
    assert sep7[0].session == 1
    assert sep7[1].session == 2


def test_first_session_times():
    msgs = parse_file(FIXTURE)
    sessions = extract_sessions(msgs, source_file="sample_chat.txt")
    first = next(s for s in sessions if s.date == date(2023, 9, 7) and s.session == 1)
    assert first.online_time == time(17, 8)
    assert first.offline_time == time(20, 30)


def test_duration_computed():
    msgs = parse_file(FIXTURE)
    sessions = extract_sessions(msgs, source_file="sample_chat.txt")
    first = next(s for s in sessions if s.date == date(2023, 9, 7) and s.session == 1)
    assert first.duration_hours == round((20 * 60 + 30 - 17 * 60 - 8) / 60, 2)


def test_unpaired_online_has_null_offline():
    # Sep 21 has only a conditional message — should produce 0 sessions
    msgs = parse_file(FIXTURE)
    sessions = extract_sessions(msgs, source_file="sample_chat.txt")
    sep21 = [s for s in sessions if s.date == date(2023, 9, 21)]
    assert len(sep21) == 0


def test_source_file_stored():
    msgs = parse_file(FIXTURE)
    sessions = extract_sessions(msgs, source_file="sample_chat.txt")
    assert all(s.source_file == "sample_chat.txt" for s in sessions)
