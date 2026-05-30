"""Date parsing utilities."""

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import dateparser


MONTHS_RU = {
    "январь": 1,
    "января": 1,
    "январе": 1,
    "февраль": 2,
    "февраля": 2,
    "феврале": 2,
    "март": 3,
    "марта": 3,
    "марте": 3,
    "апрель": 4,
    "апреля": 4,
    "апреле": 4,
    "май": 5,
    "мая": 5,
    "мае": 5,
    "июнь": 6,
    "июня": 6,
    "июне": 6,
    "июль": 7,
    "июля": 7,
    "июле": 7,
    "август": 8,
    "августа": 8,
    "августе": 8,
    "сентябрь": 9,
    "сентября": 9,
    "сентябре": 9,
    "октябрь": 10,
    "октября": 10,
    "октябре": 10,
    "ноябрь": 11,
    "ноября": 11,
    "ноябре": 11,
    "декабрь": 12,
    "декабря": 12,
    "декабре": 12,
}

TIME_WORDS = {
    "утро": (9, 0),
    "утром": (9, 0),
    "день": (13, 0),
    "днем": (13, 0),
    "днём": (13, 0),
    "обед": (13, 0),
    "обедом": (13, 0),
    "вечер": (19, 0),
    "вечером": (19, 0),
    "ночь": (22, 0),
    "ночью": (22, 0),
}


def _normalize(value: str) -> str:
    """Normalize user text before parsing."""
    value = value.strip().lower().replace("ё", "е")
    value = value.replace(",", ":")
    value = re.sub(r"(?<=\d)\.(?=\d)", ":", value)
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"\bв\s+(?=\d|полдень|полночь)", "", value)
    return value.strip()


def parse_time_fragment(value: str) -> tuple[int, int]:
    """
    Parse a user-friendly time fragment.

    Accepts: 10, 10:30, 10.30, 10 30, 1030, утром, вечером, полдень.
    """
    raw = _normalize(value)

    if raw in {"полдень", "к полудню"}:
        return 12, 0
    if raw in {"полночь", "к полуночи"}:
        return 0, 0
    if raw in TIME_WORDS:
        return TIME_WORDS[raw]

    match = re.fullmatch(r"(\d{1,2})(?::(\d{1,2}))?", raw)
    spaced_match = re.fullmatch(r"(\d{1,2})\s+(\d{1,2})", raw)
    compact_match = re.fullmatch(r"\d{3,4}", raw)

    if compact_match:
        hour = int(raw[:-2])
        minute = int(raw[-2:])
    elif spaced_match:
        hour = int(spaced_match.group(1))
        minute = int(spaced_match.group(2))
    elif match:
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
    else:
        raise ValueError(f"Invalid time: {value}")

    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError(f"Invalid time: {value}")
    return hour, minute


def _extract_time_from_text(value: str) -> tuple[int, int] | None:
    """Extract a time fragment from a larger date phrase."""
    raw = _normalize(value)

    for word, parsed in TIME_WORDS.items():
        if re.search(rf"\b{re.escape(word)}\b", raw):
            return parsed
    if re.search(r"\bполдень\b", raw):
        return 12, 0
    if re.search(r"\bполночь\b", raw):
        return 0, 0

    time_patterns = [
        r"(?:^|\s)(?:в|к|на)?\s*([01]?\d|2[0-3])[:.](\d{1,2})(?:\s|$)",
        r"(?:^|\s)(?:в|к|на)\s+([01]?\d|2[0-3])(?:\s|$)",
        r"(?:^|\s)([01]?\d|2[0-3])\s*(?:час|часа|часов|ч)(?:\s|$)",
        r"(?:^|\s)([01]?\d|2[0-3])(?:\s|$)",
    ]
    for pattern in time_patterns:
        match = re.search(pattern, raw)
        if not match:
            continue
        hour = int(match.group(1))
        minute = int(match.group(2) or 0) if len(match.groups()) > 1 else 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
    return None


def _parse_relative_datetime(value: str, tz: ZoneInfo) -> datetime | None:
    """Parse stable relative Russian phrases before dateparser fallback."""
    raw = _normalize(value)
    match = re.fullmatch(
        r"(?:через|спустя)\s+(\d+(?:[.:]\d+)?)\s*"
        r"(минуту|минуты|минут|мин|м|час|часа|часов|ч|день|дня|дней|дн|сутки|неделю|недели|недель|нед)",
        raw,
    )
    if not match:
        return None

    amount = float(match.group(1).replace(":", "."))
    unit = match.group(2)
    if unit.startswith(("мин", "м")):
        delta = timedelta(minutes=amount)
    elif unit.startswith(("час", "ч")):
        delta = timedelta(hours=amount)
    elif unit.startswith(("день", "дня", "дней", "дн", "сут")):
        delta = timedelta(days=amount)
    else:
        delta = timedelta(weeks=amount)

    return datetime.now(tz) + delta


def _parse_named_day_datetime(value: str, tz: ZoneInfo) -> datetime | None:
    """Parse today/tomorrow/day-after-tomorrow phrases with optional time."""
    raw = _normalize(value)
    today = datetime.now(tz).date()
    day_offset = None
    if re.search(r"\bсегодня\b", raw):
        day_offset = 0
    elif re.search(r"\bпослезавтра\b", raw):
        day_offset = 2
    elif re.search(r"\bзавтра\b", raw):
        day_offset = 1

    if day_offset is None:
        return None

    parsed_time = _extract_time_from_text(raw)
    hour, minute = parsed_time or (9, 0)
    selected = today + timedelta(days=day_offset)
    return datetime(selected.year, selected.month, selected.day, hour, minute, tzinfo=tz)


def _parse_month_name_datetime(value: str, tz: ZoneInfo) -> datetime | None:
    """Parse phrases like '28 мая 15:00' or '28 мая в 15'."""
    raw = _normalize(value)
    match = re.search(
        r"\b(\d{1,2})\s+("
        + "|".join(sorted(MONTHS_RU.keys(), key=len, reverse=True))
        + r")(?:\s+(\d{2,4}))?\b",
        raw,
    )
    if not match:
        return None

    day = int(match.group(1))
    month = MONTHS_RU[match.group(2)]
    now = datetime.now(tz)
    year = int(match.group(3)) if match.group(3) else now.year
    if year < 100:
        year += 2000

    parsed_time = _extract_time_from_text(raw[match.end():])
    hour, minute = parsed_time or (9, 0)
    result = datetime(year, month, day, hour, minute, tzinfo=tz)
    if result < now and not match.group(3):
        result = result.replace(year=year + 1)
    return result


def parse_datetime(date_str: str, timezone: str = "Europe/Moscow") -> datetime:
    """
    Parse datetime from string with natural language support.
    
    Supports:
    - "сегодня 18:30"
    - "завтра 9"
    - "послезавтра вечером"
    - "28 мая 15:00"
    - "2026-02-20 15:30"
    - "через 2 часа"
    
    Args:
        date_str: Date string to parse
        timezone: User timezone
    
    Returns:
        datetime in specified timezone
    """
    tz = ZoneInfo(timezone)
    normalized = _normalize(date_str)

    for parser in (
        _parse_relative_datetime,
        _parse_named_day_datetime,
        _parse_month_name_datetime,
    ):
        result = parser(normalized, tz)
        if result is not None:
            return result
    
    result = dateparser.parse(
        normalized,
        languages=["ru", "en"],
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
