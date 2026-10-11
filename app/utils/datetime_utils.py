"""
Centralized datetime utilities for consistent timestamp handling.

Provides a single source of truth for naive UTC datetime generation
to prevent arithmetic errors when comparing timezone-aware and timezone-naive datetimes.
"""
from datetime import datetime, timezone


def get_naive_utc_now() -> datetime:
    """
    Get current UTC time as a naive datetime (without timezone info).
    
    This is required by psycopg2 driver and the database schema.
    Using this utility function ensures consistent timestamp handling
    across all modules and prevents arithmetic errors when comparing
    timezone-aware and timezone-naive datetimes.
    
    Returns:
        datetime: Current UTC time without timezone info
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_naive_utc(dt: datetime) -> datetime:
    """
    Convert a timezone-aware datetime to naive UTC.
    
    Args:
        dt: Datetime object (may be timezone-aware or naive)
        
    Returns:
        datetime: Naive UTC datetime
    """
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt
