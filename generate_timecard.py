#!/usr/bin/env python3
"""
Generate a timecard for 曉寒 from the chat history.
"""

import re
import csv
import os
from collections import defaultdict

EVENTS_FILE = "/Users/mikeshih/.claude/projects/-Users-mikeshih-code-buyplus1-helper/d1f293b5-3eba-466a-9c3d-4859f22826f0/tool-results/toolu_01AjRUq5BBCR6GP84iQHDRiR.txt"
DATES_FILE  = "/Users/mikeshih/.claude/projects/-Users-mikeshih-code-buyplus1-helper/d1f293b5-3eba-466a-9c3d-4859f22826f0/tool-results/toolu_017R2eo4ub5ThKJffBL6Wtrt.txt"
OUTPUT_FILE = "/Users/mikeshih/code/buyplus1-helper/references/timecard/timecard_曉寒.csv"

# ── 1. Load date boundaries ────────────────────────────────────────────────
date_boundaries = []   # list of (start_line, date_str)

with open(DATES_FILE, encoding="utf-8") as f:
    for raw in f:
        raw = raw.strip()
        if not raw:
            continue
        # Format: "LINENO:YYYY.MM.DD Weekday"
        m = re.match(r'^(\d+):(20\d\d\.\d\d\.\d\d)\s+\w+', raw)
        if m:
            date_boundaries.append((int(m.group(1)), m.group(2)))

date_boundaries.sort(key=lambda x: x[0])

def get_date_for_line(lineno):
    date = None
    for start, d in date_boundaries:
        if start <= lineno:
            date = d
        else:
            break
    return date

# ── 2. Classify each event message ────────────────────────────────────────
def classify(msg):
    """Returns 'online', 'offline', or None."""
    if any(p in msg for p in ['上線', '回來上線']):
        return 'online'
    if any(p in msg for p in ['先下', '下線', '先離開', '先來下']):
        return 'offline'
    return None

# ── 3. Load events ─────────────────────────────────────────────────────────
events = []

with open(EVENTS_FILE, encoding="utf-8") as f:
    for raw in f:
        raw = raw.strip()
        if not raw:
            continue
        # Format: "LINENO:HH:MM 曉寒 MESSAGE"
        m = re.match(r'^(\d+):(\d{2}:\d{2})\s+曉寒\s+(.+)$', raw)
        if not m:
            continue
        lineno = int(m.group(1))
        time   = m.group(2)
        msg    = m.group(3).strip()
        kind   = classify(msg)
        if kind:
            events.append({
                'lineno': lineno,
                'time':   time,
                'msg':    msg,
                'kind':   kind,
                'date':   get_date_for_line(lineno),
            })

print(f"Loaded {len(events)} classified events")

# ── 4. Group events by date ────────────────────────────────────────────────
by_date = defaultdict(list)
for ev in events:
    if ev['date']:
        by_date[ev['date']].append(ev)

print(f"Dates with events: {len(by_date)}")

# ── 5. Time helpers ────────────────────────────────────────────────────────
def time_to_min(t):
    h, m = map(int, t.split(':'))
    return h * 60 + m

def gap_minutes(off_time, on_time):
    """Minutes from off_time to on_time, handling midnight wrap."""
    diff = time_to_min(on_time) - time_to_min(off_time)
    if diff < -60:
        diff += 24 * 60
    return diff

# ── 6. Session logic ───────────────────────────────────────────────────────
def process_day(date, day_events):
    """
    Build sessions for one day.

    Algorithm:
    - Walk through events in order.
    - On ONLINE: begin (or continue) a session block.
    - On OFFLINE: record as "latest offline" in current block.
    - On ONLINE after a previous OFFLINE:
        - If gap <= 120 min → temporary return, same session
        - If gap >  120 min → close prior session, start new one
    - At end of day: close the open session with last_offline (or mark incomplete).
    - Entirely skip leading OFFLINEs (no session started yet).
    """
    sessions = []
    in_session = False
    session_online_time = None
    session_online_msg  = None
    last_offline        = None

    for ev in sorted(day_events, key=lambda e: e['lineno']):
        if ev['kind'] == 'online':
            if not in_session:
                # Fresh session start
                in_session = True
                session_online_time = ev['time']
                session_online_msg  = ev['msg']
                last_offline = None
            else:
                # Already in a session — is this a return from temp leave?
                if last_offline is not None:
                    gap = gap_minutes(last_offline['time'], ev['time'])
                    if gap <= 120:
                        # Temporary return → same session, clear last_offline
                        last_offline = None
                    else:
                        # Real end of previous session; start new one
                        sessions.append({
                            'date':         date,
                            'session':      0,  # will renumber
                            'online_time':  session_online_time,
                            'offline_time': last_offline['time'],
                            'online_msg':   session_online_msg,
                            'offline_msg':  last_offline['msg'],
                        })
                        session_online_time = ev['time']
                        session_online_msg  = ev['msg']
                        last_offline = None
                # else: two online in a row with no offline → probably a repeated
                # announcement; keep the first start time, ignore this one

        else:  # offline
            if not in_session:
                # Offline before any online — skip
                continue
            last_offline = ev  # always update to latest offline in block

    # Close out
    if in_session:
        if last_offline:
            sessions.append({
                'date':         date,
                'session':      0,
                'online_time':  session_online_time,
                'offline_time': last_offline['time'],
                'online_msg':   session_online_msg,
                'offline_msg':  last_offline['msg'],
            })
        else:
            sessions.append({
                'date':         date,
                'session':      0,
                'online_time':  session_online_time,
                'offline_time': '???',
                'online_msg':   session_online_msg,
                'offline_msg':  '[no offline found]',
            })

    # Renumber sessions
    for idx, s in enumerate(sessions, 1):
        s['session'] = idx

    return sessions


# ── 7. Build full timecard ─────────────────────────────────────────────────
all_sessions = []
for date in sorted(by_date.keys()):
    day_sessions = process_day(date, by_date[date])
    all_sessions.extend(day_sessions)

# ── 8. Write CSV ───────────────────────────────────────────────────────────
os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['date', 'session', 'online_time', 'offline_time', 'online_msg', 'offline_msg'])
    for s in all_sessions:
        writer.writerow([
            s['date'], s['session'],
            s['online_time'], s['offline_time'],
            s['online_msg'],  s['offline_msg'],
        ])

print(f"\nWritten {len(all_sessions)} sessions to {OUTPUT_FILE}")

incomplete = [s for s in all_sessions if s['offline_time'] == '???']
print(f"Total sessions     : {len(all_sessions)}")
print(f"Incomplete sessions: {len(incomplete)}")
if incomplete:
    print("\nIncomplete (no offline found):")
    for s in incomplete:
        print(f"  {s['date']} session {s['session']}: online {s['online_time']} | {s['online_msg']}")

# Sample output
print("\nFirst 10 rows:")
for s in all_sessions[:10]:
    print(f"  {s['date']} | s{s['session']} | {s['online_time']}→{s['offline_time']} | {s['online_msg'][:30]!r} | {s['offline_msg'][:30]!r}")
