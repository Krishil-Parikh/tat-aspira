"""Schedule parser for laboratory batch schedules.

Parses strings like:
  - "Tue / Fri 6 pm"         → [(1, 18:00), (4, 18:00)]
  - "Daily 9 am to 7 pm"     → [(0..6, 09:00)] (batch at start time)
  - "Daily 3 pm"             → [(0..6, 15:00)]
  - "Mon to Fri 3 pm"        → [(0..4, 15:00)]
  - "Wed/ Sat 6 pm"          → [(2, 18:00), (5, 18:00)]
  - "1st & 3rd Thu 5 pm"     → [(3, 17:00)] with week-of-month info
  - "Tue/ Thu/ Sat 10 am"    → [(1, 10:00), (3, 10:00), (5, 10:00)]
  - "Mon / Wed / Thu / Sat 3 pm" → multiple days
  - "Refer Individual Test"  → empty (profile tests)
  
Returns list of (day_of_week: 0=Mon..6=Sun, hour: int, minute: int) tuples.
For monthly schedules (1st & 3rd), includes week_numbers field.
"""

import re
from datetime import datetime, time, timedelta
from typing import List, Tuple, Optional, NamedTuple


class BatchSlot(NamedTuple):
    """A single batch slot."""
    day_of_week: int  # 0=Monday, 6=Sunday
    hour: int
    minute: int
    week_numbers: Optional[List[int]] = None  # For "1st & 3rd" type schedules


DAY_MAP = {
    "mon": 0, "monday": 0,
    "tue": 1, "tuesday": 1, "tues": 1,
    "wed": 2, "wednesday": 2,
    "thu": 3, "thursday": 3, "thur": 3, "thurs": 3, "thue": 3,
    "fri": 4, "friday": 4,
    "sat": 5, "saturday": 5,
    "sun": 6, "sunday": 6,
}

ORDINAL_MAP = {
    "1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5,
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
}


def parse_time_str(time_str: str) -> Tuple[int, int]:
    """Parse a time string like '6 pm', '9 am', '12 pm' into (hour, minute)."""
    time_str = time_str.strip().lower()
    
    # Try "H:MM am/pm" format
    m = re.match(r'(\d{1,2}):(\d{2})\s*(am|pm)', time_str)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        if m.group(3) == 'pm' and hour != 12:
            hour += 12
        elif m.group(3) == 'am' and hour == 12:
            hour = 0
        return (hour, minute)

    # Try "H am/pm" format
    m = re.match(r'(\d{1,2})\s*(am|pm)', time_str)
    if m:
        hour = int(m.group(1))
        if m.group(2) == 'pm' and hour != 12:
            hour += 12
        elif m.group(2) == 'am' and hour == 12:
            hour = 0
        return (hour, 0)

    return (12, 0)  # Default noon


def parse_schedule(schedule_str: str) -> List[BatchSlot]:
    """Parse a test schedule string into batch slots."""
    if not schedule_str:
        return []

    schedule_str = schedule_str.strip()

    # Skip non-parseable schedules
    skip_patterns = ["refer individual", "walk in"]
    if any(p in schedule_str.lower() for p in skip_patterns):
        return []

    # ---- Handle "Daily" schedules ----
    if schedule_str.lower().startswith("daily"):
        rest = schedule_str[5:].strip()

        # "Daily 9 am to 7 pm" → batch at start time each day
        m = re.match(r'(\d{1,2}\s*(?:am|pm))\s*to\s*(\d{1,2}\s*(?:am|pm))', rest, re.IGNORECASE)
        if m:
            hour, minute = parse_time_str(m.group(1))
            return [BatchSlot(d, hour, minute) for d in range(7)]

        # "Daily 3 pm"
        m = re.match(r'(\d{1,2}(?::\d{2})?\s*(?:am|pm))', rest, re.IGNORECASE)
        if m:
            hour, minute = parse_time_str(m.group(1))
            return [BatchSlot(d, hour, minute) for d in range(7)]

        # "Daily 12 pm & 4 pm" or "Daily 12 pm, 6 PM"
        times = re.findall(r'(\d{1,2}(?::\d{2})?\s*(?:am|pm))', rest, re.IGNORECASE)
        if times:
            slots = []
            for t in times:
                hour, minute = parse_time_str(t)
                for d in range(7):
                    slots.append(BatchSlot(d, hour, minute))
            return slots

        # Fallback for "Daily" with no time → assume 6 PM
        return [BatchSlot(d, 18, 0) for d in range(7)]

    # ---- Handle "Mon to Fri" range schedules ----
    m = re.match(r'(\w+)\s*to\s*(\w+)\s+(.*)', schedule_str, re.IGNORECASE)
    if m:
        start_day = DAY_MAP.get(m.group(1).lower().strip())
        end_day = DAY_MAP.get(m.group(2).lower().strip())
        time_part = m.group(3).strip()

        if start_day is not None and end_day is not None:
            hour, minute = parse_time_str(time_part)
            days = []
            d = start_day
            while True:
                days.append(d)
                if d == end_day:
                    break
                d = (d + 1) % 7
            return [BatchSlot(d, hour, minute) for d in days]

    # ---- Handle "1st & 3rd Thu 5 pm" monthly schedules ----
    m = re.match(r'([\d\w]+(?:\s*[&/,]\s*[\d\w]+)*)\s+(\w+)\s+(.*)', schedule_str, re.IGNORECASE)
    if m:
        ordinals_str = m.group(1)
        potential_day = m.group(2).lower().strip()
        time_part = m.group(3).strip()

        # Check if the second capture is a day name
        if potential_day in DAY_MAP:
            # Extract ordinals
            ordinals = re.findall(r'(\d+(?:st|nd|rd|th)|\w+)', ordinals_str, re.IGNORECASE)
            week_nums = []
            for o in ordinals:
                o_lower = o.lower().strip()
                if o_lower in ORDINAL_MAP:
                    week_nums.append(ORDINAL_MAP[o_lower])

            if week_nums:
                hour, minute = parse_time_str(time_part)
                return [BatchSlot(DAY_MAP[potential_day], hour, minute, week_nums)]

    # ---- Handle day list schedules: "Tue / Fri 6 pm", "Tue/ Thu/ Sat 10 am" ----
    # Extract all day names
    tokens = re.split(r'[/,&]+', schedule_str)
    days_found = []
    time_str = ""

    for token in tokens:
        token = token.strip()
        # Try to find day name at start of token
        words = token.split()
        if words:
            first_word = words[0].lower().strip()
            if first_word in DAY_MAP:
                days_found.append(DAY_MAP[first_word])
                # Remaining words might be the time
                remaining = " ".join(words[1:]).strip()
                if remaining:
                    time_str = remaining

    # Also try to extract time from the end of the full string
    if not time_str:
        time_match = re.search(r'(\d{1,2}(?::\d{2})?\s*(?:am|pm))', schedule_str, re.IGNORECASE)
        if time_match:
            time_str = time_match.group(1)

    if days_found and time_str:
        hour, minute = parse_time_str(time_str)
        return [BatchSlot(d, hour, minute) for d in days_found]

    # ---- Fallback: try to extract any time ----
    time_match = re.search(r'(\d{1,2}(?::\d{2})?\s*(?:am|pm))', schedule_str, re.IGNORECASE)
    if time_match:
        hour, minute = parse_time_str(time_match.group(1))
        # If we can't determine days, assume daily
        return [BatchSlot(d, hour, minute) for d in range(7)]

    return []


def find_next_batch(accession_time: datetime, schedule_str: str) -> Optional[datetime]:
    """Find the next available batch after the given accession time.
    
    Args:
        accession_time: When the sample was received
        schedule_str: The test schedule string from CSV
        
    Returns:
        The datetime of the next batch, or None if schedule can't be parsed
    """
    slots = parse_schedule(schedule_str)
    if not slots:
        return None

    # Try the next 35 days to find a matching batch
    best_batch = None

    for days_ahead in range(0, 35):
        candidate_date = accession_time.date() + timedelta(days=days_ahead)
        candidate_dow = candidate_date.weekday()  # 0=Monday

        for slot in slots:
            if slot.day_of_week != candidate_dow:
                continue

            # Check week-of-month for "1st & 3rd" type schedules
            if slot.week_numbers:
                week_of_month = (candidate_date.day - 1) // 7 + 1
                if week_of_month not in slot.week_numbers:
                    continue

            batch_dt = datetime.combine(candidate_date, time(slot.hour, slot.minute))

            # Batch must be after accession time
            if batch_dt > accession_time:
                if best_batch is None or batch_dt < best_batch:
                    best_batch = batch_dt
                    return best_batch  # First valid future batch is the closest

    return best_batch
