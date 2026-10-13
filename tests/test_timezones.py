"""Hand-typed timezone names must never break reminders."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.config import settings
from src.db.models import RepeatRule, User
from src.repositories.user_repo import UserRepository
from src.utils.timezones import (
    EXPLICIT_UTC,
    canonical_timezone_name,
    normalize_user_timezone_choice,
    safe_zoneinfo,
)
from src.worker.reminder_worker import ReminderWorkerService


@pytest.mark.parametrize(
    "typed, expected",
    [
        ("europe/moscow", "Europe/Moscow"),
        ("EUROPE/MOSCOW", "Europe/Moscow"),
        ("  Asia/Tokyo ", "Asia/Tokyo"),
        ("america/new_york", "America/New_York"),
    ],
)
def test_typed_timezone_is_stored_in_canonical_spelling(typed, expected):
    assert normalize_user_timezone_choice(typed) == expected


def test_unknown_timezone_is_rejected():
    assert normalize_user_timezone_choice("Mars/Olympus") is None
    assert canonical_timezone_name("") is None


@pytest.mark.parametrize("typed", ["UTC", "utc", "Etc/UTC", "GMT"])
def test_explicit_utc_choice_is_not_confused_with_legacy_default(typed):
    assert normalize_user_timezone_choice(typed) == EXPLICIT_UTC


def test_safe_zoneinfo_falls_back_instead_of_raising():
    assert str(safe_zoneinfo("europe/moscow")) == "Europe/Moscow"
    assert str(safe_zoneinfo("nonsense", "Europe/Moscow")) == "Europe/Moscow"


@pytest.mark.asyncio
async def test_get_or_create_heals_lowercase_timezone(db_session):
    user = User(telegram_id=88001, timezone="europe/moscow")
    db_session.add(user)
    await db_session.flush()

    healed = await UserRepository(db_session).get_or_create(telegram_id=88001)

    assert healed.timezone == "Europe/Moscow"


@pytest.mark.asyncio
async def test_get_or_create_keeps_explicit_utc_choice(db_session):
    user = User(telegram_id=88002, timezone=EXPLICIT_UTC)
    db_session.add(user)
    await db_session.flush()

    kept = await UserRepository(db_session).get_or_create(telegram_id=88002)

    assert kept.timezone == EXPLICIT_UTC


def test_worker_formats_reminder_for_lowercase_timezone():
    """Before the fix this raised ZoneInfoNotFoundError and the reminder never arrived."""
    worker = ReminderWorkerService(bot=None)
    reminder = SimpleNamespace(
        id=1,
        title="Таблетка",
        text="Принять",
        remind_at_utc=datetime(2026, 10, 14, 6, 0, tzinfo=timezone.utc),
        repeat_rule=RepeatRule.NONE,
        user=SimpleNamespace(telegram_id=1, timezone="europe/moscow"),
    )

    text = worker._format_reminder_message(reminder)

    assert "14.10.2026 09:00 (Europe/Moscow)" in text


def test_worker_falls_back_to_default_for_unknown_timezone(monkeypatch):
    monkeypatch.setattr(settings, "TIMEZONE_DEFAULT", "Europe/Moscow")
    worker = ReminderWorkerService(bot=None)
    reminder = SimpleNamespace(user=SimpleNamespace(timezone="Mars/Olympus"))

    assert worker._get_user_timezone(reminder) == "Europe/Moscow"
