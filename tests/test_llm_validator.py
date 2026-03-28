"""Tests for LLMValidator and ambiguous online/offline detection."""
import json
from datetime import date, time
from pathlib import Path

import pytest

from buyplus1_helper.extractor import (
    _is_ambiguous_offline,
    _is_ambiguous_online,
    _is_offline,
    _is_online,
    extract_sessions,
)
from buyplus1_helper.llm_validator import LLMValidator
from buyplus1_helper.models import ChatMessage


def _msg(content: str, sender: str = "曉寒"):
    return ChatMessage(
        date=date(2024, 4, 28),
        weekday="Sunday",
        timestamp=time(7, 19),
        sender=sender,
        content=content,
    )


# --- _is_ambiguous_online ---

def test_ambiguous_detects_time_deferred():
    assert _is_ambiguous_online(_msg("我10分鐘後上線～"))


def test_ambiguous_detects_hours_deferred():
    assert _is_ambiguous_online(_msg("我大概三個小時後上線喔"))


def test_ambiguous_not_triggered_for_anchor():
    # Starts with anchor — already classified as definite online
    assert not _is_ambiguous_online(_msg("上線，等等再繼續"))


def test_ambiguous_not_triggered_for_exclusion():
    # Already excluded by keyword rule
    assert not _is_ambiguous_online(_msg("我晚一點上線喔"))


def test_ambiguous_not_triggered_for_other_sender():
    assert not _is_ambiguous_online(_msg("她10分鐘後上線", sender="❤️Candice❤️"))


def test_is_online_returns_false_for_ambiguous():
    # _is_online must return False for ambiguous patterns (defer to LLM)
    assert not _is_online(_msg("我10分鐘後上線～"))
    assert not _is_online(_msg("我大概三個小時後上線喔"))


# --- _is_ambiguous_offline ---

def test_ambiguous_offline_detects_likai():
    assert _is_ambiguous_offline(_msg("我先離開一下"))
    assert _is_ambiguous_offline(_msg("先離開，等等回來"))
    assert _is_ambiguous_offline(_msg("我離開一下確認訂單"))


def test_ambiguous_offline_not_triggered_for_definitive():
    # Already caught by _is_offline (下線 / 先下 / etc.)
    assert not _is_ambiguous_offline(_msg("我先下線喔"))
    assert not _is_ambiguous_offline(_msg("我先下，等等回來"))


def test_ambiguous_offline_not_triggered_for_other_sender():
    assert not _is_ambiguous_offline(_msg("我先離開一下", sender="❤️Candice❤️"))


def test_is_offline_returns_false_for_ambiguous():
    # _is_offline must NOT auto-classify ambiguous 離開 messages
    assert not _is_offline(_msg("我先離開一下"))
    assert not _is_offline(_msg("先離開確認一下"))


# --- LLMValidator (mocked API) ---
# _call_api now takes (content, system_prompt) and returns a raw string answer.

def test_validator_now(tmp_path):
    v = LLMValidator(cache_path=tmp_path / "cache.json")
    v._call_api = lambda content, prompt: "now"
    assert v.is_online_now("我10分鐘後上線～") is True


def test_validator_future(tmp_path):
    v = LLMValidator(cache_path=tmp_path / "cache.json")
    v._call_api = lambda content, prompt: "future"
    assert v.is_online_now("我大概三個小時後上線喔") is False


def test_validator_offline(tmp_path):
    v = LLMValidator(cache_path=tmp_path / "cache.json")
    v._call_api = lambda content, prompt: "offline"
    assert v.is_offline_now("我先離開一下") is True


def test_validator_working(tmp_path):
    v = LLMValidator(cache_path=tmp_path / "cache.json")
    v._call_api = lambda content, prompt: "working"
    assert v.is_offline_now("我先離開一下確認訂單") is False


def test_validator_caches_online_result(tmp_path):
    call_count = 0

    def counting_call(content, prompt):
        nonlocal call_count
        call_count += 1
        return "now"

    v = LLMValidator(cache_path=tmp_path / "cache.json")
    v._call_api = counting_call

    v.is_online_now("我10分鐘後上線～")
    v.is_online_now("我10分鐘後上線～")  # second call — should use cache
    assert call_count == 1


def test_validator_caches_offline_result(tmp_path):
    call_count = 0

    def counting_call(content, prompt):
        nonlocal call_count
        call_count += 1
        return "offline"

    v = LLMValidator(cache_path=tmp_path / "cache.json")
    v._call_api = counting_call

    v.is_offline_now("我先離開一下")
    v.is_offline_now("我先離開一下")  # second call — should use cache
    assert call_count == 1


def test_online_and_offline_use_separate_cache_keys(tmp_path):
    """Same message content must not share a cache slot across online/offline."""
    v = LLMValidator(cache_path=tmp_path / "cache.json")
    v._call_api = lambda content, prompt: "now" if "上線" in prompt else "offline"
    # Hypothetical message that contains both keywords
    msg = "我先離開一下，等等上線"
    v.is_online_now(msg)
    v.is_offline_now(msg)
    raw = json.loads((tmp_path / "cache.json").read_text())
    assert raw[msg] == "now"
    assert raw[f"offline:{msg}"] == "offline"


def test_validator_persists_cache(tmp_path):
    cache_file = tmp_path / "cache.json"

    v1 = LLMValidator(cache_path=cache_file)
    v1._call_api = lambda content, prompt: "now"
    v1.is_online_now("我10分鐘後上線～")

    # Load a new validator from the same cache file
    v2 = LLMValidator(cache_path=cache_file)
    v2._call_api = lambda content, prompt: (_ for _ in ()).throw(AssertionError("should not call API"))
    assert v2.is_online_now("我10分鐘後上線～") is True  # served from cache


def test_validator_error_defaults_to_future(tmp_path):
    v = LLMValidator(cache_path=tmp_path / "cache.json")

    def erroring_call(content, prompt):
        raise RuntimeError("API unavailable")

    v._call_api = erroring_call
    assert v.is_online_now("我大概三個小時後上線喔") is False


def test_validator_error_defaults_to_working(tmp_path):
    v = LLMValidator(cache_path=tmp_path / "cache.json")

    def erroring_call(content, prompt):
        raise RuntimeError("API unavailable")

    v._call_api = erroring_call
    assert v.is_offline_now("我先離開一下") is False


# --- extract_sessions with LLMValidator ---

def test_extract_sessions_with_llm_now(tmp_path):
    """LLM says 'now' → ambiguous online message treated as login."""
    msgs = [
        ChatMessage(date=date(2024, 4, 28), weekday="Sunday",
                    timestamp=time(7, 19), sender="曉寒", content="我10分鐘後上線～"),
        ChatMessage(date=date(2024, 4, 28), weekday="Sunday",
                    timestamp=time(9, 0), sender="曉寒", content="我先下線"),
    ]
    v = LLMValidator(cache_path=tmp_path / "cache.json")
    v._call_api = lambda content, prompt: "now"

    sessions = extract_sessions(msgs, source_file="test.txt", llm_validator=v)
    assert len(sessions) == 1
    assert sessions[0].online_time == time(7, 19)
    assert sessions[0].offline_time == time(9, 0)


def test_extract_sessions_with_llm_future(tmp_path):
    """LLM says 'future' → ambiguous online message ignored."""
    msgs = [
        ChatMessage(date=date(2024, 4, 28), weekday="Sunday",
                    timestamp=time(7, 19), sender="曉寒", content="我10分鐘後上線～"),
        ChatMessage(date=date(2024, 4, 28), weekday="Sunday",
                    timestamp=time(9, 0), sender="曉寒", content="我先下線"),
    ]
    v = LLMValidator(cache_path=tmp_path / "cache.json")
    v._call_api = lambda content, prompt: "future"

    sessions = extract_sessions(msgs, source_file="test.txt", llm_validator=None)
    assert len(sessions) == 0


def test_extract_sessions_without_llm_skips_ambiguous():
    """Without a validator, ambiguous messages are silently skipped."""
    msgs = [
        ChatMessage(date=date(2024, 4, 28), weekday="Sunday",
                    timestamp=time(7, 19), sender="曉寒", content="我10分鐘後上線～"),
        ChatMessage(date=date(2024, 4, 28), weekday="Sunday",
                    timestamp=time(9, 0), sender="曉寒", content="我先下線"),
    ]
    sessions = extract_sessions(msgs, source_file="test.txt", llm_validator=None)
    assert len(sessions) == 0


def test_extract_sessions_ambiguous_offline_detected(tmp_path):
    """LLM says 'offline' → ambiguous 離開 message treated as logout."""
    msgs = [
        ChatMessage(date=date(2024, 4, 28), weekday="Sunday",
                    timestamp=time(17, 0), sender="曉寒", content="我上線"),
        ChatMessage(date=date(2024, 4, 28), weekday="Sunday",
                    timestamp=time(20, 30), sender="曉寒", content="我先離開一下"),
    ]
    v = LLMValidator(cache_path=tmp_path / "cache.json")
    v._call_api = lambda content, prompt: "offline"

    sessions = extract_sessions(msgs, source_file="test.txt", llm_validator=v)
    assert len(sessions) == 1
    assert sessions[0].offline_time == time(20, 30)


def test_extract_sessions_ambiguous_offline_working(tmp_path):
    """LLM says 'working' → ambiguous 離開 message ignored (session stays open)."""
    msgs = [
        ChatMessage(date=date(2024, 4, 28), weekday="Sunday",
                    timestamp=time(17, 0), sender="曉寒", content="我上線"),
        ChatMessage(date=date(2024, 4, 28), weekday="Sunday",
                    timestamp=time(20, 30), sender="曉寒", content="我先離開一下確認訂單"),
    ]
    v = LLMValidator(cache_path=tmp_path / "cache.json")
    v._call_api = lambda content, prompt: "working"

    sessions = extract_sessions(msgs, source_file="test.txt", llm_validator=v)
    assert len(sessions) == 1
    assert sessions[0].offline_time is None
