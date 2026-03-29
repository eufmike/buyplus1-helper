"""Full LLM-based session extractor using Gemini.

Instead of keyword rules, sends 曉寒's messages to Gemini and asks it to
identify work sessions directly.  The design is intentionally simple:

- One session per calendar day in Taiwan Time (UTC+8).
- Messages from the LINE export (Pacific Time device clock) are converted to
  Taiwan Time before grouping and before being sent to the LLM.  This avoids
  midnight-crossing sessions: a session that starts at 22:00 PT is 14:00 TW
  the next calendar day — entirely within one TW day.
- TimecardEntry.online_time / offline_time store Taiwan Time directly.
- Messages are split into per-day (TW) chunks and processed in parallel via
  ThreadPoolExecutor.
- A post-processing step (_merge_to_one_per_day) collapses any multiple
  sessions the LLM returns for the same day into a single entry.
- A state file alongside the master CSV records the last fully-processed date
  so that subsequent runs only send the newly unseen portion of a chat export.
"""
from __future__ import annotations

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, time, timedelta
from itertools import groupby
from pathlib import Path
from typing import Optional

from .models import ChatMessage, TimecardEntry
from .llm_validator import _load_env
from .timecard import _pt_utc_offset

logger = logging.getLogger(__name__)

TARGET_SENDER = "曉寒"

_DEFAULT_MODEL = "gemini-2.5-flash-lite"


def _messages_to_tw(messages: list[ChatMessage]) -> list[ChatMessage]:
    """Convert ChatMessage timestamps from Pacific Time to Taiwan Time (UTC+8).

    The LINE export uses the device's local clock (Pacific Time).  Converting
    to TW before chunking means all of 曉寒's evening sessions (e.g. 22:xx PT)
    become afternoon sessions (14:xx TW the next calendar day), eliminating
    midnight-crossing sessions entirely.
    """
    result: list[ChatMessage] = []
    weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    for m in messages:
        if m.timestamp is None:
            result.append(m)
            continue
        pt_offset = _pt_utc_offset(m.date)   # -7 (PDT) or -8 (PST)
        # PT → UTC → TW(+8)
        total_min = m.timestamp.hour * 60 + m.timestamp.minute
        total_min -= pt_offset * 60           # to UTC
        total_min += 8 * 60                   # to TW
        day_delta = total_min // (24 * 60)    # 0 (same day) or 1 (next day)
        total_min %= 24 * 60
        tw_time = time(total_min // 60, total_min % 60)
        tw_date = m.date + timedelta(days=day_delta)
        result.append(m.model_copy(update={
            "date": tw_date,
            "weekday": weekday_names[tw_date.weekday()],
            "timestamp": tw_time,
        }))
    return result


_SYSTEM_PROMPT = """\
你是一個工時記錄助理。以下是客服人員「曉寒」當天在工作群組的訊息紀錄（只有她的訊息）。
所有時間均為台灣時間（Asia/Taipei，UTC+8）。

你的任務：找出她當天所有的上線/下線段落（含中途暫時離開），以計算實際工時。

規則：
1. 上線宣告（例：我上線、上線、回來了、回來上線）→ 開始一個新的 segment（start）
2. 下線宣告（例：先下線、先下、先來下、我下線、離線、先閃）→ 結束當前 segment（end）
3. 每次中途離開再回來，算獨立的 segment；暫時離開的時間不計入工時
4. 如果最後一個 segment 沒有下線宣告，end 填 null
5. 如果當天完全沒有上線宣告，回傳空陣列 []

回傳 JSON 陣列，每天最多一個元素：
[
  {
    "date": "YYYY-MM-DD",
    "segments": [
      {"start": "HH:MM", "end": "HH:MM"},
      {"start": "HH:MM", "end": null}
    ]
  }
]

只回傳 JSON，不要 markdown 標記，不要任何其他文字。\
"""


def _format_batch(messages: list[ChatMessage]) -> str:
    """Render messages as plain text grouped by day (曉寒-only messages)."""
    lines: list[str] = []
    current_day: Optional[date] = None
    for m in sorted(messages, key=lambda m: (m.date, m.timestamp or time.min)):
        if m.date != current_day:
            current_day = m.date
            lines.append(f"\n{m.date} {m.weekday}")
        ts = m.timestamp.strftime("%H:%M") if m.timestamp else "??"
        lines.append(f"{ts} {m.content}")
    return "\n".join(lines).strip()


def _split_into_daily_chunks(
    messages: list[ChatMessage],
) -> list[tuple[date, list[ChatMessage]]]:
    """Split messages into per-day chunks.

    Returns a list of (target_date, day_messages) tuples,
    one per calendar day that has messages, in chronological order.
    """
    by_date: dict[date, list[ChatMessage]] = {}
    for m in messages:
        by_date.setdefault(m.date, []).append(m)

    return [(d, by_date[d]) for d in sorted(by_date)]


def _merge_to_one_per_day(entries: list[TimecardEntry]) -> list[TimecardEntry]:
    """Collapse all entries for the same day into a single session.

    online_time        = earliest non-null online_time
    offline_time       = latest non-null offline_time (None if all null)
    duration_hours     = sum of individual durations (net working time, excl. temp leave)
    temp_leave_minutes = total span - net working time
    session            = always 1
    """
    by_date: dict[date, list[TimecardEntry]] = {}
    for e in entries:
        by_date.setdefault(e.date, []).append(e)

    result: list[TimecardEntry] = []
    for d in sorted(by_date):
        day = by_date[d]
        if len(day) == 1:
            day[0].session = 1
            result.append(day[0])
            continue

        online_times = [e.online_time for e in day if e.online_time is not None]
        offline_times = [e.offline_time for e in day if e.offline_time is not None]
        online_t = min(online_times) if online_times else None
        offline_t = max(offline_times) if offline_times else None

        # Sum individual net durations rather than recomputing from span
        dur_values = [e.duration_hours for e in day if e.duration_hours is not None]
        duration: Optional[float] = round(sum(dur_values), 2) if dur_values else None

        temp_leave: Optional[float] = None
        if online_t and offline_t and duration is not None:
            span_min = (offline_t.hour - online_t.hour) * 60 + (offline_t.minute - online_t.minute)
            if span_min < 0:  # cross-midnight session
                span_min += 24 * 60
            temp_leave = max(0.0, round(span_min - duration * 60, 1))

        merged = day[0]
        merged.session = 1
        merged.online_time = online_t
        merged.offline_time = offline_t
        merged.duration_hours = duration
        merged.temp_leave_minutes = temp_leave
        result.append(merged)

    return result


def _renumber_sessions(entries: list[TimecardEntry]) -> list[TimecardEntry]:
    """Re-assign session numbers (1-based) per day, sorted by online_time."""
    by_date: dict[date, list[TimecardEntry]] = {}
    for e in entries:
        by_date.setdefault(e.date, []).append(e)

    result: list[TimecardEntry] = []
    for d in sorted(by_date):
        day_entries = sorted(by_date[d], key=lambda e: e.online_time or time.min)
        for i, e in enumerate(day_entries, start=1):
            e.session = i
            result.append(e)
    return result


def _parse_response(raw: str, source_file: str) -> list[TimecardEntry]:
    """Parse Gemini's JSON response into TimecardEntry objects.

    Expected format per item:
      {"date": "YYYY-MM-DD", "segments": [{"start": "HH:MM", "end": "HH:MM"}, ...]}

    Computes:
      online_time        = earliest segment start
      offline_time       = latest segment end (None if last segment has no end)
      duration_hours     = sum of completed segment durations (net working time)
      temp_leave_minutes = total span - net working time (gap between segments)
    """
    text = raw.strip()
    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse LLM response as JSON: %s\nRaw: %s", exc, text[:500])
        return []

    if isinstance(parsed, dict):
        items: list[dict] = [parsed]
    elif isinstance(parsed, list):
        items = parsed
    else:
        logger.error("Unexpected JSON type %s in LLM response", type(parsed).__name__)
        return []

    entries: list[TimecardEntry] = []
    for item in items:
        try:
            d = date.fromisoformat(item["date"])
            segments = item.get("segments", [])

            starts: list[time] = []
            ends: list[time] = []
            worked_minutes = 0.0

            for seg in segments:
                start_raw = seg.get("start")
                end_raw = seg.get("end")
                if not start_raw:
                    continue
                st = time.fromisoformat(start_raw)
                starts.append(st)
                if end_raw:
                    en = time.fromisoformat(end_raw)
                    ends.append(en)
                    seg_min = (en.hour - st.hour) * 60 + (en.minute - st.minute)
                    if seg_min < 0:  # cross-midnight segment
                        seg_min += 24 * 60
                    worked_minutes += seg_min

            online_t: Optional[time] = min(starts) if starts else None
            offline_t: Optional[time] = max(ends) if ends else None

            duration: Optional[float] = round(worked_minutes / 60, 2) if worked_minutes > 0 else None

            temp_leave: Optional[float] = None
            if online_t and offline_t and duration is not None:
                span_min = (offline_t.hour - online_t.hour) * 60 + (offline_t.minute - online_t.minute)
                if span_min < 0:  # cross-midnight session
                    span_min += 24 * 60
                temp_leave = max(0.0, round(span_min - worked_minutes, 1))

            weekday = item.get("weekday", d.strftime("%A"))
            entries.append(
                TimecardEntry(
                    date=d,
                    weekday=weekday,
                    session=1,
                    online_time=online_t,
                    offline_time=offline_t,
                    duration_hours=duration,
                    temp_leave_minutes=temp_leave,
                    source_file=source_file,
                    notes=item.get("notes", ""),
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping malformed session item %r: %s", item, exc)

    return entries


class LLMExtractor:
    """Extract 曉寒's work sessions from chat messages using Gemini.

    Messages are split into per-day chunks and processed in parallel.
    Each chunk includes the previous day's messages as context to handle
    sessions that span midnight.
    """

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        max_workers: int = 4,
    ) -> None:
        self._model = model
        self._max_workers = max_workers
        _load_env()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_sessions(
        self,
        messages: list[ChatMessage],
        source_file: str = "",
        from_date: Optional[date] = None,
    ) -> list[TimecardEntry]:
        """Return work sessions extracted by Gemini.

        Args:
            messages:    All parsed chat messages (all senders).
            source_file: Stored in each entry for traceability.
            from_date:   If set, only process messages on or after this date.
                         Pass the day after the last already-processed date for
                         incremental runs.
        """
        # Keep only 曉寒's messages, optionally from a start date (PT dates)
        xh = [
            m for m in messages
            if m.sender == TARGET_SENDER
            and (from_date is None or m.date >= from_date)
        ]
        if not xh:
            logger.info("No new messages to process.")
            return []

        # Convert PT timestamps → Taiwan Time so that daily chunks are by TW
        # date.  Evening PT sessions (22:xx) become afternoon TW sessions
        # (14:xx next TW day), eliminating midnight-crossing sessions.
        xh = _messages_to_tw(xh)

        # Group into monthly batches for logging, then process each month in parallel daily chunks
        def month_key(m: ChatMessage) -> tuple[int, int]:
            return (m.date.year, m.date.month)

        all_entries: list[TimecardEntry] = []
        months = groupby(sorted(xh, key=lambda m: (m.date, m.timestamp or time.min)), key=month_key)
        for (year, month), batch_iter in months:
            batch = list(batch_iter)
            logger.info("Processing %d-%02d: %d messages across %d day(s)",
                        year, month, len(batch), len({m.date for m in batch}))
            entries = self._process_month_parallel(batch, source_file)
            all_entries.extend(entries)

        return all_entries

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _process_month_parallel(
        self, messages: list[ChatMessage], source_file: str
    ) -> list[TimecardEntry]:
        """Process one month's messages by splitting into daily chunks, run in parallel.

        By the time this is called, messages are already in Taiwan Time, so
        daily chunks are clean TW calendar days with no midnight crossings.
        """
        chunks = _split_into_daily_chunks(messages)

        if len(chunks) == 1:
            target_date, day_msgs = chunks[0]
            return self._process_batch(day_msgs, source_file)

        all_entries: list[TimecardEntry] = []
        futures_map = {}

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            for target_date, day_msgs in chunks:
                future = executor.submit(self._process_batch, day_msgs, source_file)
                futures_map[future] = target_date

            for future in as_completed(futures_map):
                target_date = futures_map[future]
                try:
                    entries = future.result()
                    all_entries.extend(entries)
                except Exception as exc:  # noqa: BLE001
                    logger.error("Chunk failed for %s: %s — skipping", target_date, exc)

        all_entries = _merge_to_one_per_day(all_entries)
        all_entries = _renumber_sessions(all_entries)
        logger.info("  → %d session(s) extracted", len(all_entries))
        return all_entries

    def _process_batch(
        self,
        messages: list[ChatMessage],
        source_file: str,
    ) -> list[TimecardEntry]:
        """Send one day's messages to Gemini and return parsed entries."""
        text = _format_batch(messages)
        try:
            raw = self._call_api(text)
        except Exception as exc:  # noqa: BLE001
            logger.error("API call failed for batch: %s", exc)
            return []

        entries = _parse_response(raw, source_file)

        # Backfill weekday from message data if LLM omitted it
        date_to_weekday = {m.date: m.weekday for m in messages}
        for e in entries:
            if not e.weekday and e.date in date_to_weekday:
                e.weekday = date_to_weekday[e.date]

        # Safety net: collapse any multiple entries for the same day into one
        entries = _merge_to_one_per_day(entries)

        return entries

    def _call_api(self, text: str) -> str:
        import time as _time
        from google import genai
        from google.genai import types

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY not set. Add it to .env or export it as an env var."
            )

        client = genai.Client(api_key=api_key)
        last_exc: Exception | None = None
        for attempt in range(5):
            try:
                response = client.models.generate_content(
                    model=self._model,
                    contents=text,
                    config=types.GenerateContentConfig(
                        system_instruction=_SYSTEM_PROMPT,
                        temperature=0.0,
                    ),
                )
                return response.text
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                # Retry on 503 / rate-limit; bail immediately on auth errors
                err_str = str(exc)
                if "503" in err_str or "429" in err_str or "UNAVAILABLE" in err_str:
                    wait = 2 ** attempt  # 1, 2, 4, 8, 16 seconds
                    logger.warning("API error (attempt %d/5): %s — retrying in %ds", attempt + 1, exc, wait)
                    _time.sleep(wait)
                else:
                    raise
        raise RuntimeError(f"All 5 API attempts failed: {last_exc}") from last_exc


# ------------------------------------------------------------------
# State helpers (last-processed-date watermark)
# ------------------------------------------------------------------

def load_state(state_path: Path) -> dict:
    if state_path.exists():
        try:
            return json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {}


def save_state(state_path: Path, last_date: date) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state = load_state(state_path)
    state["last_processed_date"] = str(last_date)
    state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def get_from_date(state_path: Path) -> Optional[date]:
    """Return the first date to process (day after last processed), or None."""
    state = load_state(state_path)
    raw = state.get("last_processed_date")
    if not raw:
        return None
    return date.fromisoformat(raw) - timedelta(days=1)  # reprocess last day for safety
