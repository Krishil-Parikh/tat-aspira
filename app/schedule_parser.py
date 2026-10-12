"""
Schedule parser for laboratory batch schedules.

Parses strings like:
  "Tue / Fri 6 pm"               → [(1,18:00), (4,18:00)]
  "Daily 9 am to 7 pm"           → every day at 09:00
  "Daily 3 pm"                   → every day at 15:00
  "Mon to Fri 3 pm"              → Mon-Fri at 15:00
  "1st & 3rd Thu 5 pm"           → specific weeks of month
  "Tue/ Thu/ Sat 10 am"          → three days at 10:00
  "Daily 12 pm & 4 pm"           → two slots per day
  "Refer Individual Test"        → [] (profile/panel)
"""
from __future__ import annotations
import re
from datetime import datetime, time, timedelta
from typing import List, NamedTuple, Optional, Tuple


class BatchSlot(NamedTuple):
    day_of_week:  int             # 0=Mon … 6=Sun
    hour:         int
    minute:       int
    week_numbers: Optional[List[int]] = None   # None → every occurrence


DAY_MAP: dict[str, int] = {
    "mon": 0, "monday": 0,
    "tue": 1, "tuesday": 1, "tues": 1,
    "wed": 2, "wednesday": 2,
    "thu": 3, "thursday": 3, "thur": 3, "thurs": 3, "thue": 3,
    "fri": 4, "friday": 4,
    "sat": 5, "saturday": 5,
    "sun": 6, "sunday": 6,
}

ORDINAL_MAP: dict[str, int] = {
    "1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5,
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
}

_TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", re.IGNORECASE)


def _parse_time(s: str) -> Tuple[int, int]:
    """Return (hour24, minute) from a string containing an am/pm time."""
    m = _TIME_RE.search(s)
    if not m:
        return (18, 0)              # default 6 PM
    hour   = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    ampm   = m.group(3).lower()
    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    return (hour, minute)


def _all_times(s: str) -> List[Tuple[int, int]]:
    """Extract all am/pm times from a string."""
    return [
        _parse_time(m.group(0))
        for m in _TIME_RE.finditer(s)
    ]


def parse_schedule(schedule_str: str) -> List[BatchSlot]:
    """Parse a test schedule string into a list of BatchSlots."""
    if not schedule_str:
        return []

    raw = schedule_str.strip()
    low = raw.lower()

    # Skip non-parseable markers
    if any(p in low for p in ("refer individual", "walk in")):
        return []

    # ── Daily ──────────────────────────────────────────────────────────────
    if low.startswith("daily"):
        rest = raw[5:].strip()

        # "Daily 9 am to 7 pm" → batch at open time, every day
        m = re.match(r"(\d{1,2}(?::\d{2})?\s*(?:am|pm))\s*to\s*\d", rest, re.IGNORECASE)
        if m:
            h, mi = _parse_time(m.group(1))
            return [BatchSlot(d, h, mi) for d in range(7)]

        # "Daily 12 pm & 4 pm"  or  "Daily 3 pm"
        times = _all_times(rest)
        if times:
            slots: List[BatchSlot] = []
            for (h, mi) in times:
                slots.extend(BatchSlot(d, h, mi) for d in range(7))
            return slots

        # bare "Daily" → 6 PM
        return [BatchSlot(d, 18, 0) for d in range(7)]

    # ── "Mon to Fri H pm" range ─────────────────────────────────────────────
    m = re.match(r"(\w+)\s*to\s*(\w+)\s+(.*)", raw, re.IGNORECASE)
    if m:
        s_day = DAY_MAP.get(m.group(1).lower().strip())
        e_day = DAY_MAP.get(m.group(2).lower().strip())
        if s_day is not None and e_day is not None:
            h, mi = _parse_time(m.group(3))
            days: List[int] = []
            d = s_day
            while True:
                days.append(d)
                if d == e_day:
                    break
                d = (d + 1) % 7
            return [BatchSlot(day, h, mi) for day in days]

    # ── "1st & 3rd Thu 5 pm" monthly ────────────────────────────────────────
    m = re.match(
        r"((?:[\d\w]+(?:\s*[&,]\s*[\d\w]+)*))\s+(\w+)\s+(.*)",
        raw, re.IGNORECASE
    )
    if m:
        potential_day = m.group(2).lower().strip()
        if potential_day in DAY_MAP:
            ordinals = re.findall(
                r"(\d+(?:st|nd|rd|th)|\w+)", m.group(1), re.IGNORECASE
            )
            week_nums = [
                ORDINAL_MAP[o.lower()]
                for o in ordinals
                if o.lower() in ORDINAL_MAP
            ]
            if week_nums:
                h, mi = _parse_time(m.group(3))
                return [BatchSlot(DAY_MAP[potential_day], h, mi, week_nums)]

    # ── "Tue / Fri 6 pm"  /  "Tue/ Thu/ Sat 10 am" day-list ───────────────
    tokens = re.split(r"[/,&]+", raw)
    days_found: List[int] = []
    time_str   = ""

    for token in tokens:
        words = token.strip().split()
        if not words:
            continue
        first = words[0].lower().rstrip(".")
        if first in DAY_MAP:
            days_found.append(DAY_MAP[first])
            remainder = " ".join(words[1:])
            if remainder and _TIME_RE.search(remainder):
                time_str = remainder

    if not time_str:
        tm = _TIME_RE.search(raw)
        if tm:
            time_str = tm.group(0)

    if days_found and time_str:
        h, mi = _parse_time(time_str)
        return [BatchSlot(d, h, mi) for d in days_found]

    # ── Fallback: any time → assume daily ────────────────────────────────────
    tm = _TIME_RE.search(raw)
    if tm:
        h, mi = _parse_time(tm.group(0))
        return [BatchSlot(d, h, mi) for d in range(7)]

    return []


def find_next_batch(
    accession_time: datetime,
    schedule_str:   str,
    horizon_days:   int = 35,
) -> Optional[datetime]:
    """
    Return the earliest future batch datetime after *accession_time*.

    Searches up to *horizon_days* ahead.  Returns None only when the
    schedule string is genuinely unparseable (e.g. 'Refer Individual Test').
    """
    slots = parse_schedule(schedule_str)
    if not slots:
        return None

    for days_ahead in range(0, horizon_days):
        candidate_date = accession_time.date() + timedelta(days=days_ahead)
        candidate_dow  = candidate_date.weekday()

        for slot in slots:
            if slot.day_of_week != candidate_dow:
                continue

            # Monthly occurrence filter
            if slot.week_numbers:
                week_of_month = (candidate_date.day - 1) // 7 + 1
                if week_of_month not in slot.week_numbers:
                    continue

            # Carry tz-info from accession_time if present
            if accession_time.tzinfo is not None:
                import pytz
                tz = accession_time.tzinfo
                batch_dt = datetime(
                    candidate_date.year, candidate_date.month, candidate_date.day,
                    slot.hour, slot.minute, tzinfo=tz
                )
            else:
                batch_dt = datetime.combine(
                    candidate_date, time(slot.hour, slot.minute)
                )

            if batch_dt > accession_time:
                return batch_dt

    return None
