"""Tests for LLMValidator and ambiguous online detection."""
import json
from datetime import date, time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from buyplus1_helper.extractor import _is_ambiguous_online, _is_online, extract_sessions
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


# --- LLMValidator (mocked API) ---

def _make_validator(tmp_path: Path, answer: str = "now") -> LLMValidator:
    """Build a validator whose API call returns the given answer."""
    validator = LLMValidator(cache_path=tmp_path / "cache.json")

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=answer)]

    with patch("anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = mock_response
        # Trigger lazy import path by patching inside the module
        with patch("buyplus1_helper.llm_validator.anthropic") as mock_anthropic:
            mock_anthropic.Anthropic.return_value.messages.create.return_value = mock_response
            validator._call_api = lambda content: answer == "now"

    return validator


def test_validator_now(tmp_path):
    v = LLMValidator(cache_path=tmp_path / "cache.json")
    v._call_api = lambda _: True   # mock: always "now"
    assert v.is_online_now("我10分鐘後上線～") is True


def test_validator_future(tmp_path):
    v = LLMValidator(cache_path=tmp_path / "cache.json")
    v._call_api = lambda _: False  # mock: always "future"
    assert v.is_online_now("我大概三個小時後上線喔") is False


def test_validator_caches_result(tmp_path):
    call_count = 0

    def counting_call(content):
        nonlocal call_count
        call_count += 1
        return True

    v = LLMValidator(cache_path=tmp_path / "cache.json")
    v._call_api = counting_call

    v.is_online_now("我10分鐘後上線～")
    v.is_online_now("我10分鐘後上線～")  # second call — should use cache
    assert call_count == 1


def test_validator_persists_cache(tmp_path):
    cache_file = tmp_path / "cache.json"

    v1 = LLMValidator(cache_path=cache_file)
    v1._call_api = lambda _: True
    v1.is_online_now("我10分鐘後上線～")

    # Load a new validator from the same cache file
    v2 = LLMValidator(cache_path=cache_file)
    v2._call_api = lambda _: (_ for _ in ()).throw(AssertionError("should not call API"))
    assert v2.is_online_now("我10分鐘後上線～") is True  # served from cache


def test_validator_error_defaults_to_future(tmp_path):
    v = LLMValidator(cache_path=tmp_path / "cache.json")

    def raise_error(content):
        raise RuntimeError("API unavailable")

    v._call_api = raise_error
    # On error, _call_api raises, but is_online_now catches it
    # Since we patched _call_api directly, simulate error path via the real method
    original = v._call_api
    def erroring_call_api(content):
        raise RuntimeError("API unavailable")
    v._call_api = erroring_call_api

    # The exception is caught inside is_online_now → returns False
    assert v.is_online_now("我大概三個小時後上線喔") is False


# --- extract_sessions with LLMValidator ---

def test_extract_sessions_with_llm_now(tmp_path):
    """LLM says 'now' → ambiguous message treated as online."""
    msgs = [
        ChatMessage(date=date(2024, 4, 28), weekday="Sunday",
                    timestamp=time(7, 19), sender="曉寒", content="我10分鐘後上線～"),
        ChatMessage(date=date(2024, 4, 28), weekday="Sunday",
                    timestamp=time(9, 0), sender="曉寒", content="我先下線"),
    ]
    v = LLMValidator(cache_path=tmp_path / "cache.json")
    v._call_api = lambda _: True  # "now"

    sessions = extract_sessions(msgs, source_file="test.txt", llm_validator=v)
    assert len(sessions) == 1
    assert sessions[0].online_time == time(7, 19)
    assert sessions[0].offline_time == time(9, 0)


def test_extract_sessions_with_llm_future(tmp_path):
    """LLM says 'future' → ambiguous message ignored."""
    msgs = [
        ChatMessage(date=date(2024, 4, 28), weekday="Sunday",
                    timestamp=time(7, 19), sender="曉寒", content="我10分鐘後上線～"),
        ChatMessage(date=date(2024, 4, 28), weekday="Sunday",
                    timestamp=time(9, 0), sender="曉寒", content="我先下線"),
    ]
    v = LLMValidator(cache_path=tmp_path / "cache.json")
    v._call_api = lambda _: False  # "future"

    sessions = extract_sessions(msgs, source_file="test.txt", llm_validator=v)
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
