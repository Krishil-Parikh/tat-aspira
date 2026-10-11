"""
TAT (Turnaround Time) parser.

Parses strings like:
  "Same Day"           → +0 days, 18:00
  "Same Day 5 Hrs"     → +5 hours from batch
  "Same Day 6 PM"      → +0 days, 18:00
  "Next Day 8 pm"      → +1 day, 20:00
  "3rd Day 7 pm"       → +3 days, 19:00
  "48 Hrs"             → +2 days 0h (i.e. 48 h offset)
  "22 Days"            → +22 days, 18:00
  "3 to 5 Days"        → +5 days (take max), 18:00
  "Mon 10 pm"          → +2 days approx, 22:00
  "Preliminary … Final report 5th Day" → +5 days, 18:00
  "As per individual"  → None (skip)

Returns (days_offset: int, hour: int, minute: int) or None.
"""
from __future__ import annotations
import re
from datetime import datetime, timedelta, time
from typing import Optional, Tuple


_TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", re.IGNORECASE)

_SKIP = frozenset(["as per individual", "refer individual", "genexpert"])

DAY_MAP = {
    "mon": 0, "monday": 0,
    "tue": 1, "tuesday": 1,
    "wed": 2, "wednesday": 2,
    "thu": 3, "thursday": 3,
    "fri": 4, "friday": 4,
    "sat": 5, "saturday": 5,
    "sun": 6, "sunday": 6,
}


DEFAULT_CLOSING_HOUR = 18
DEFAULT_CLOSING_MINUTE = 0

def _parse_time(s: str) -> Tuple[int, int]:
    m = _TIME_RE.search(s)
    if not m:
        return (DEFAULT_CLOSING_HOUR, DEFAULT_CLOSING_MINUTE)
    hour   = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    if m.group(3).lower() == "pm" and hour != 12:
        hour += 12
    elif m.group(3).lower() == "am" and hour == 12:
        hour = 0
    return (hour, minute)


def parse_tat(tat_str: str) -> Optional[Tuple[int, int, int]]:
    """
    Parse a TAT string.

    Returns (days_offset, hour_or_hours, minute) or None.

    Interpretation:
      - days_offset == 0 and 'hr' in original string  →  treat hour_or_hours
        as a raw hours delta from batch time.
      - otherwise  →  move batch_date forward by days_offset, set clock to
        (hour_or_hours, minute).
    """
    if not tat_str:
        return None

    raw   = tat_str.strip()
    low   = raw.lower()

    if any(p in low for p in _SKIP):
        return None

    # ── Same Day ──────────────────────────────────────────────────────────────
    if "same day" in low or "same  day" in low:
        m = re.search(r"same\s*day\s+(\d+)\s*hr", low)
        if m:
            return (0, int(m.group(1)), 0)        # raw-hours delta

        m = re.search(r"same\s*day\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))", raw, re.IGNORECASE)
        if m:
            h, mi = _parse_time(m.group(1))
            return (0, h, mi)

        return (0, DEFAULT_CLOSING_HOUR, DEFAULT_CLOSING_MINUTE)

    # ── Next Day ──────────────────────────────────────────────────────────────
    if re.search(r"next\s*day", low):
        m = re.search(r"next\s*day\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))", raw, re.IGNORECASE)
        if m:
            h, mi = _parse_time(m.group(1))
            return (1, h, mi)
        return (1, DEFAULT_CLOSING_HOUR, DEFAULT_CLOSING_MINUTE)

    # ── Nth Day H pm  (e.g. "3rd Day 7 pm") ─────────────────────────────────
    m = re.match(r"(\d+)(?:st|nd|rd|th)?\s*day\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))", raw, re.IGNORECASE)
    if m:
        return (int(m.group(1)), *_parse_time(m.group(2)))

    # ── Nth Day (no time) ────────────────────────────────────────────────────
    m = re.match(r"(\d+)(?:st|nd|rd|th)?\s*day\b", raw, re.IGNORECASE)
    if m:
        return (int(m.group(1)), DEFAULT_CLOSING_HOUR, DEFAULT_CLOSING_MINUTE)

    # ── "Final report Nth Day" ────────────────────────────────────────────────
    m = re.search(r"final\s*report\s+(\d+)(?:st|nd|rd|th)?\s*day", raw, re.IGNORECASE)
    if m:
        return (int(m.group(1)), DEFAULT_CLOSING_HOUR, DEFAULT_CLOSING_MINUTE)

    # ── N Hrs  (e.g. "48 Hrs") ───────────────────────────────────────────────
    m = re.match(r"(\d+)\s*hrs?", raw, re.IGNORECASE)
    if m:
        hours = int(m.group(1))
        # Store as raw-hours: caller uses timedelta(hours=hours)
        return (0, hours, 0)

    # ── N to M Hrs (take max) ─────────────────────────────────────────────────
    m = re.match(r"(\d+)\s*to\s*(\d+)\s*hrs?", raw, re.IGNORECASE)
    if m:
        return (0, int(m.group(2)), 0)

    # ── N Days ───────────────────────────────────────────────────────────────
    m = re.match(r"(\d+)\s*days?", raw, re.IGNORECASE)
    if m:
        return (int(m.group(1)), 18, 0)

    # ── N to M Days (take max) ───────────────────────────────────────────────
    m = re.match(r"(\d+)\s*to\s*(\d+)\s*days?", raw, re.IGNORECASE)
    if m:
        return (int(m.group(2)), DEFAULT_CLOSING_HOUR, DEFAULT_CLOSING_MINUTE)

    # ── Specific named day  "Mon 10 pm" ──────────────────────────────────────
    m = re.match(r"(mon|tue|wed|thu|fri|sat|sun)\w*\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))", raw, re.IGNORECASE)
    if m:
        h, mi = _parse_time(m.group(2))
        return (2, h, mi)     # conservative 2-day approximation

    # ── Preliminary report N to M Hrs ────────────────────────────────────────
    m = re.search(r"(\d+)\s*to\s*(\d+)\s*hrs?", raw, re.IGNORECASE)
    if m:
        hours = int(m.group(2))
        return (0, hours, 0)

    return None


def calculate_eta(batch_time: datetime, tat_str: str) -> Optional[datetime]:
    """
    Compute expected report datetime from batch start and TAT rule.

    Handles both:
      - Raw-hours rules  ("48 Hrs", "Same Day 5 Hrs")
      - Day-offset + clock rules  ("Next Day 8 pm", "3rd Day 7 pm")
    """
    parsed = parse_tat(tat_str)
    if parsed is None:
        return None

    days_offset, hour_or_hours, minute = parsed
    low = tat_str.lower()

    # Raw-hours delta: days_offset==0 and the string contains 'hr'
    if days_offset == 0 and "hr" in low:
        return batch_time + timedelta(hours=hour_or_hours, minutes=minute)

    # Day-offset + specific clock
    from datetime import time as _time
    eta_date = batch_time.date() + timedelta(days=days_offset)
    eta_time = _time(hour_or_hours, minute)

    if batch_time.tzinfo is not None:
        import pytz
        tz = batch_time.tzinfo
        return datetime(
            eta_date.year, eta_date.month, eta_date.day,
            hour_or_hours, minute, tzinfo=tz
        )

    return datetime.combine(eta_date, eta_time)
