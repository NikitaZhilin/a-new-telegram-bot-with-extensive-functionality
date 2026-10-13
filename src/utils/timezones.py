"""Timezone name helpers.

Users can type a timezone by hand. pytz accepts names in any letter case
("europe/moscow"), but zoneinfo on Linux only knows the canonical spelling
("Europe/Moscow"). Storing the raw text made every later ZoneInfo() call fail,
so reminders for that user were never delivered. These helpers turn any
accepted spelling into the canonical name and give a safe fallback.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

# Explicit UTC choice is stored as "Etc/UTC": plain "UTC" is the legacy
# column default and is still auto-migrated to TIMEZONE_DEFAULT for users
# who never picked a timezone.
EXPLICIT_UTC = "Etc/UTC"
_UTC_ALIASES = {"utc", "etc/utc", "gmt", "etc/gmt", "z", "zulu", "universal", "etc/universal"}


@lru_cache(maxsize=1)
def _canonical_by_lower() -> dict[str, str]:
    return {name.lower(): name for name in available_timezones()}


def canonical_timezone_name(value: Optional[str]) -> Optional[str]:
    """Return the canonical IANA name for value, or None if it is unknown."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        ZoneInfo(raw)
        return raw
    except (ZoneInfoNotFoundError, ValueError):
        pass
    return _canonical_by_lower().get(raw.lower())


def normalize_user_timezone_choice(value: str) -> Optional[str]:
    """Canonical name for a timezone the user typed or picked; None if unknown.

    An explicit UTC choice is stored as Etc/UTC so it is not mistaken for the
    legacy "UTC" default and silently replaced by TIMEZONE_DEFAULT.
    """
    if value is None:
        return None
    raw = str(value).strip()
    if raw.lower() in _UTC_ALIASES:
        return EXPLICIT_UTC
    return canonical_timezone_name(raw)


def safe_timezone_name(value: Optional[str], default: str) -> str:
    """Canonical timezone name for value, falling back to default."""
    return canonical_timezone_name(value) or canonical_timezone_name(default) or "UTC"


def safe_zoneinfo(value: Optional[str], default: str = "UTC") -> ZoneInfo:
    """ZoneInfo for value that never raises on a bad stored name."""
    return ZoneInfo(safe_timezone_name(value, default))
