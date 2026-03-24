# Spec: Timecard Parser

## Purpose

Parse LINE group chat history exports to extract 曉寒's online/offline timestamps,
then produce and maintain a master CSV spreadsheet she can use to sign her timecard.

---

## User Story

> 曉寒 announces "我上線" / "我先下線" in a shared LINE chat group each work session.
> At the end of the month she needs a signed timecard. This tool extracts those
> timestamps automatically so she doesn't have to scan the chat manually.

---

## Input: Chat History File

### Format

```
2023.09.07 Thursday
17:08 曉寒 我上線
18:09 ❤️Candice❤️ @曉寒 那人是神經病
20:30 曉寒 我先來下線接小孩
22:01 曉寒 回來上線
23:35 曉寒 我先下線喔
2023.09.08 Friday
00:32 廖育瑩 ...
```

### Rules

- **Date header**: `YYYY.MM.DD DayOfWeek` (English weekday, dot-separated date)
- **Message**: `HH:MM SenderName MessageContent`
- **Continuation lines**: lines that start without `HH:MM` are continuations of the
  previous message and are ignored for timecard purposes.

---

## Detection Rules

### Online events (sender must be `曉寒`)

The message content must contain `上線` **and** must NOT match any exclusion pattern:

| Pattern | Example | Include? |
|---------|---------|---------|
| `我上線` | `17:08 曉寒 我上線` | ✅ |
| `上線` | `17:07 曉寒 上線` | ✅ |
| `回來上線` | `22:01 曉寒 回來上線` | ✅ |
| `我上線來發匯款通知` | `07:26 曉寒 我上線來發匯款通知` | ✅ |
| `我上限` (typo) | `17:07 曉寒 我上限` | ✅ treated as 上線 |
| `我下午有空會再上線處理` | conditional | ❌ excluded |
| `曉寒妳有再上線的話` | other sender | ❌ excluded (wrong sender) |

### Offline events (sender must be `曉寒`)

The message content must contain `下線`:

| Pattern | Example | Include? |
|---------|---------|---------|
| `我先下線喔` | `23:35 曉寒 我先下線喔` | ✅ |
| `先來下線` | `08:29 曉寒 先來下線` | ✅ |
| `我先下線` | `22:14 曉寒 我先下線` | ✅ |
| `我先來下線接小孩` | `20:30 曉寒 我先來下線接小孩` | ✅ |

### Exclusion patterns for online detection

- `有空會再上線` — conditional future statement
- `有再上線的話` — other-person phrasing

---

## Session Pairing

Within each calendar day, events are paired greedily left-to-right:

```
online  → offline  → online  → offline
  session 1             session 2
```

If a day ends with an unpaired online event (no offline), the session is kept with
`offline_time = null` and `duration_hours = null`.

---

## Output: Master CSV

### Schema

| Column | Type | Notes |
|--------|------|-------|
| `date` | `YYYY-MM-DD` | Calendar date |
| `weekday` | `str` | Monday … Sunday |
| `session` | `int` | 1-indexed per day |
| `online_time` | `HH:MM` | Time went online |
| `offline_time` | `HH:MM` | Time went offline (blank if open) |
| `duration_hours` | `float` | Decimal hours (blank if open) |
| `source_file` | `str` | Filename of the source chat export |
| `notes` | `str` | Raw offline message text |

### Encoding

UTF-8 with BOM (`utf-8-sig`) so Windows Excel opens it correctly without import wizard.

### Merge / Deduplication

When merging a new parsed CSV into the master:
- Key: `(date, session)`
- If a record already exists for that key, the **newer source file wins** (overwrites).
- Records from dates not in the new file are preserved unchanged.

---

## CLI Reference

```
timecard parse  <chat_file>  [--output FILE]
    Parse a chat file and write a timecard CSV.
    Default output: <chat_file_stem>_timecard.csv

timecard merge  <input_csv>  <master_csv>
    Merge a parsed CSV into the master (creates master if missing).

timecard run    <chat_file>  <master_csv>
    Convenience: parse + merge in one step.

timecard show   <master_csv> [--from YYYY-MM-DD] [--to YYYY-MM-DD]
    Display records as a rich table to stdout.

timecard export <master_csv> [--format csv|excel] [--output FILE]
    Re-export master (useful for Excel .xlsx output).
```

---

## Edge Cases

| Situation | Handling |
|-----------|----------|
| No offline after last online | Session row kept, `offline_time` blank |
| Multiple sessions same day | Separate rows with session=1,2,3… |
| Typo `上限` instead of `上線` | Treated as online event |
| Continuation lines (no timestamp) | Ignored |
| Overlapping date ranges between exports | Deduplication by `(date, session)` |
