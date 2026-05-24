"""Recurring reminder scheduling tests."""

from datetime import datetime, timezone

from src.db.models import RepeatRule
from src.repositories.reminder_repo import calculate_next_occurrence


def test_daily_repeat_preserves_local_time_across_dst_start():
    """Daily reminders should stay at the same local clock time across DST."""
    current = datetime(2026, 3, 7, 14, 0, tzinfo=timezone.utc)  # 09:00 New York

    next_time = calculate_next_occurrence(
        current,
        RepeatRule.DAILY,
        "America/New_York",
    )

    assert next_time == datetime(2026, 3, 8, 13, 0, tzinfo=timezone.utc)  # 09:00 New York


def test_weekly_repeat_preserves_local_time_across_dst_start():
    """Weekly reminders should also preserve local clock time."""
    current = datetime(2026, 3, 1, 14, 0, tzinfo=timezone.utc)  # 09:00 New York

    next_time = calculate_next_occurrence(
        current,
        RepeatRule.WEEKLY,
        "America/New_York",
    )

    assert next_time == datetime(2026, 3, 8, 13, 0, tzinfo=timezone.utc)  # 09:00 New York


def test_monthly_repeat_preserves_last_day_semantics():
    """Monthly reminders on month end should stay on month end."""
    january = datetime(2026, 1, 31, 9, 0, tzinfo=timezone.utc)

    february = calculate_next_occurrence(january, RepeatRule.MONTHLY, "UTC")
    march = calculate_next_occurrence(february, RepeatRule.MONTHLY, "UTC")

    assert february == datetime(2026, 2, 28, 9, 0, tzinfo=timezone.utc)
    assert march == datetime(2026, 3, 31, 9, 0, tzinfo=timezone.utc)


def test_monthly_repeat_handles_leap_year_month_end():
    """Leap-year February uses the real last day of month."""
    january = datetime(2028, 1, 31, 9, 0, tzinfo=timezone.utc)

    february = calculate_next_occurrence(january, RepeatRule.MONTHLY, "UTC")

    assert february == datetime(2028, 2, 29, 9, 0, tzinfo=timezone.utc)
