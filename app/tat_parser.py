"""TAT (Turnaround Time) parser for laboratory tests.

Parses strings like:
  - "Next Day 8 pm"       → 1 day + specific time 20:00
  - "3rd Day 7 pm"        → 3 days + specific time 19:00
  - "Same Day"            → 0 days, report same day (assume end of business)
  - "Same Day 5 Hrs"      → 5 hours from batch
  - "Same Day 6 PM"       → 0 days, specific time 18:00
  - "48 Hrs"              → 48 hours
  - "22 Days"             → 22 days
  - "Next day 7 pm"       → 1 day + 19:00
  - "3rd day 5 pm"        → 3 days + 17:00
  - "Mon 10 pm"           → specific day (relative to batch)
  - "3 to 5 Days"         → take max (5 days)
  - "Next Day"            → 1 day, assume 6 PM
  - "3rd Day"             → 3 days, assume 6 PM
  - "Preliminary report 48 to 72 Hrs, Final report 5th Day" → 5 days

Returns (days_offset, hour, minute) tuple or None.
"""

import re
from datetime import datetime, timedelta, time
from typing import Optional, Tuple

DAY_MAP = {
    "mon": 0, "monday": 0,
    "tue": 1, "tuesday": 1,
    "wed": 2, "wednesday": 2,
    "thu": 3, "thursday": 3,
    "fri": 4, "friday": 4,
    "sat": 5, "saturday": 5,
    "sun": 6, "sunday": 6,
}


def parse_time_component(s: str) -> Tuple[int, int]:
    """Extract hour and minute from a time string."""
    s = s.strip().lower()
    m = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', s)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        if m.group(3) == 'pm' and hour != 12:
            hour += 12
        elif m.group(3) == 'am' and hour == 12:
            hour = 0
        return (hour, minute)
    return (18, 0)  # Default 6 PM


def parse_tat(tat_str: str) -> Optional[Tuple[int, int, int]]:
    """Parse a TAT string into (days_offset, hour, minute).
    
    Returns None if the TAT cannot be parsed.
    """
    if not tat_str:
        return None

    tat_str = tat_str.strip()
    tat_lower = tat_str.lower()

    # ---- Skip unparseable ----
    skip = ["as per individual", "refer individual", "genexpert"]
    if any(p in tat_lower for p in skip):
        return None

    # ---- "Same Day" variants ----
    if "same day" in tat_lower:
        # "Same Day 5 Hrs" or "Same Day 4hr"
        m = re.search(r'same\s*day\s+(\d+)\s*hr', tat_lower)
        if m:
            hours = int(m.group(1))
            # Return as hours offset: we'll add hours to batch time
            return (0, hours, 0)

        # "Same Day 6 PM" or "Same Day 7 pm"
        m = re.search(r'same\s*day\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))', tat_str, re.IGNORECASE)
        if m:
            hour, minute = parse_time_component(m.group(1))
            return (0, hour, minute)

        # Plain "Same Day" → assume 6 PM same day
        return (0, 18, 0)

    # ---- "Next Day" variants ----
    if "next day" in tat_lower or "next  day" in tat_lower:
        m = re.search(r'next\s+day\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))', tat_str, re.IGNORECASE)
        if m:
            hour, minute = parse_time_component(m.group(1))
            return (1, hour, minute)
        # Plain "Next Day"
        return (1, 18, 0)

    # ---- "Next day" (lowercase) with time ----
    m = re.search(r'next\s*day\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm))?', tat_str, re.IGNORECASE)
    if m and m.group(0):
        if m.group(1):
            hour, minute = parse_time_component(m.group(1))
            return (1, hour, minute)

    # ---- "Nth Day H pm" (e.g., "3rd Day 7 pm", "5th Day 9 pm") ----
    m = re.match(r'(\d+)(?:st|nd|rd|th)?\s*day\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))', tat_str, re.IGNORECASE)
    if m:
        days = int(m.group(1))
        hour, minute = parse_time_component(m.group(2))
        return (days, hour, minute)

    # ---- "Nth Day" without time ----
    m = re.match(r'(\d+)(?:st|nd|rd|th)?\s*day', tat_str, re.IGNORECASE)
    if m:
        days = int(m.group(1))
        return (days, 18, 0)

    # ---- "N Hrs" (e.g., "48 Hrs") ----
    m = re.match(r'(\d+)\s*hrs?', tat_str, re.IGNORECASE)
    if m:
        hours = int(m.group(1))
        days = hours // 24
        remaining_hours = hours % 24
        return (days, remaining_hours, 0)

    # ---- "N Days" (e.g., "22 Days", "28 Days") ----
    m = re.match(r'(\d+)\s*days?', tat_str, re.IGNORECASE)
    if m:
        days = int(m.group(1))
        return (days, 18, 0)

    # ---- "N to M Days" (e.g., "3 to 5 Days") → take max ----
    m = re.match(r'(\d+)\s*to\s*(\d+)\s*days?', tat_str, re.IGNORECASE)
    if m:
        days = int(m.group(2))  # Take the max
        return (days, 18, 0)

    # ---- Specific day: "Mon 8 pm", "Tue 7 pm" ----
    m = re.match(r'(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\w*\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))', tat_str, re.IGNORECASE)
    if m:
        # This is relative to the batch day, we approximate with days offset
        hour, minute = parse_time_component(m.group(2))
        # For "Mon 10 pm" when batch is "Sat 6 pm" → 2 days
        return (2, hour, minute)

    # ---- Complex strings with "Final report" embedded ----
    m = re.search(r'final\s*report\s+(\d+)(?:st|nd|rd|th)?\s*day', tat_str, re.IGNORECASE)
    if m:
        days = int(m.group(1))
        return (days, 18, 0)

    # ---- Preliminary with hours ----
    m = re.search(r'(\d+)\s*to\s*(\d+)\s*hrs', tat_str, re.IGNORECASE)
    if m:
        hours = int(m.group(2))  # Take max
        days = hours // 24
        remaining_hours = hours % 24
        return (days, remaining_hours, 0)

    # ---- "3day 5 pm" (no space/ordinal) ----
    m = re.match(r'(\d+)\s*day\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))', tat_str, re.IGNORECASE)
    if m:
        days = int(m.group(1))
        hour, minute = parse_time_component(m.group(2))
        return (days, hour, minute)

    return None


def calculate_eta(batch_time: datetime, tat_str: str) -> Optional[datetime]:
    """Calculate the Expected Time of Report (ETA) from batch time and TAT rule.
    
    Args:
        batch_time: When the batch starts processing
        tat_str: The TAT string from CSV
        
    Returns:
        Expected report datetime, or None if TAT can't be parsed
    """
    parsed = parse_tat(tat_str)
    if parsed is None:
        return None

    days_offset, hour_or_hours, minute = parsed

    if days_offset == 0 and "hr" in tat_str.lower() and "same day" in tat_str.lower():
        # "Same Day 5 Hrs" → add hours to batch time
        return batch_time + timedelta(hours=hour_or_hours)

    if days_offset == 0 and "hr" in tat_str.lower():
        # Pure hours offset like "48 Hrs" is already converted to days
        return batch_time + timedelta(hours=hour_or_hours)

    # Day offset with specific time
    eta_date = batch_time.date() + timedelta(days=days_offset)
    eta_time = time(hour_or_hours, minute)
    return datetime.combine(eta_date, eta_time)
