# Plan: Revised LLM Session Extractor (One Session Per Day)

## Context

The current `llm_extractor.py` produces overlapping sub-sessions and many missing
offline times. The root cause is that the LLM treats returns from temporary departures
as new sessions, fragmenting what should be a single work period.

**User's decision**: one session per day. `online_time` = first time she came online;
`offline_time` = last time she went offline. All temp departures and returns in between
are ignored. If multiple sessions are returned for the same day, merge them into one.

This eliminates the overlapping-session bug entirely at the architecture level.

---

## Approach

### 1. Revised System Prompt

Replace `_SYSTEM_PROMPT` with a simplified Chinese prompt:

```
你是一個工時記錄助理。以下是客服人員「曉寒」當天在工作群組的訊息紀錄（只有她的訊息）。
所有時間均為台灣時間（Asia/Taipei，UTC+8）。

你的任務：找出她當天的工作時間——整天只算【一段】。

規則：
1. online_time：她當天【第一次】宣告上線的時間（例：我上線、上線、回來上線）
2. offline_time：她當天【最後一次】宣告下線或離開的時間（例：先下線、先下、先來下、我下線、離線）
3. 中間所有的暫時離開、等等回來、再回來上線，全部忽略——不切割、不新增工作段
4. 如果找不到明確的下線宣告，offline_time 填 null
5. 如果當天完全沒有上線宣告，回傳空陣列 []

回傳 JSON 陣列，最多一個元素：
[
  {"date": "YYYY-MM-DD", "session": 1, "online_time": "HH:MM", "offline_time": "HH:MM"}
]

只回傳 JSON，不要 markdown 標記，不要任何其他文字。
```

Key changes from previous prompt:
- Explicitly says "整天只算一段" (one segment per day)
- Instructs to find FIRST online and LAST offline
- Says to ignore all temp departures
- Returns at most one element per day

### 2. Post-Processing: Per-Day Merge (safety net)

After `_parse_response`, if the LLM still returns multiple sessions for the same day
(hallucination), collapse them into one deterministically in `_merge_to_one_per_day`:

```python
def _merge_to_one_per_day(entries):
    # group by date
    # for each date with multiple entries:
    #   online_time  = min of all non-null online_times
    #   offline_time = max of all non-null offline_times (None if all null)
    #   session = 1, duration recomputed
    # return one entry per date
```

### 3. LLM Input Format (unchanged)

Keep sending only 曉寒's messages to the LLM.
Remove the `[前日參考]` / `context_messages` block — prev-day overlap context was
causing cross-day hallucinations.

### 4. Merge Logic Update

Change `merge()` in `timecard.py` to key on `date` instead of `(date, session)`.
All existing master rows for any date present in new data are replaced entirely,
so stale session 2/3 rows from old runs don't linger.

---

## Files Changed

| File | What changed |
|------|-------------|
| `src/buyplus1_helper/llm_extractor.py` | Replaced `_SYSTEM_PROMPT`; removed `context_messages` from `_format_batch` and `_split_into_daily_chunks`; replaced `_deduplicate_entries` with `_merge_to_one_per_day`; updated `_process_month_parallel` and `_process_batch` |
| `src/buyplus1_helper/timecard.py` | `merge()` now keys on `date` — all sessions for a reprocessed date are replaced |
| `tests/test_llm_extractor.py` | New file: 15 unit tests for `_format_batch`, `_split_into_daily_chunks`, `_merge_to_one_per_day` |

---

## Results

| Metric | Before | After |
|--------|--------|-------|
| Total rows in master CSV | 1,035 | 697 |
| Days with >1 session | 238 | 0 |
| Sessions missing offline_time | 230 (22.2%) | 111 (15.9%) |

---

## Risks

| Risk | Mitigation |
|------|-----------|
| She genuinely works two separate shifts | User decision: treat as one session spanning the gap |
| Midnight-spanning sessions | First day gets null offline_time (acceptable trade-off) |
| LLM still returns multiple sessions | `_merge_to_one_per_day` collapses them deterministically |

---

## Verification

```bash
# Run unit tests
pixi run -e test test

# Re-run on real chat file
pixi run timecard run references/timecard/chat-history-20260323.txt data/timecard_master.csv

# Check quality
python -c "
import pandas as pd
df = pd.read_csv('data/timecard_master.csv')
print('Days with >1 session:', (df.groupby('date').session.max() > 1).sum())
print('Missing offline:', df.offline_time.isna().sum())
"
```
