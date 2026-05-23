"""Date parsing utilities."""

from datetime import datetime
from zoneinfo import ZoneInfo
import dateparser


def parse_datetime(date_str: str, timezone: str = "Europe/Moscow") -> datetime:
    """
    Parse datetime from string with natural language support.
    
    Supports:
    - "сегодня 18:30"
    - "завтра 9"
    - "2026-02-20 15:30"
    - "через 2 часа"
    
    Args:
        date_str: Date string to parse
        timezone: User timezone
    
    Returns:
        datetime in specified timezone
    """
    tz = ZoneInfo(timezone)
    
    result = dateparser.parse(
        date_str,
        settings={
            'TIMEZONE': timezone,
            'RETURN_AS_TIMEZONE_AWARE': True,
            'PREFER_DATES_FROM': 'future',
            'RELATIVE_BASE': datetime.now(tz)
        }
    )
    
    if result is None:
        raise ValueError(f"Failed to parse date: {date_str}")
    
    return result
