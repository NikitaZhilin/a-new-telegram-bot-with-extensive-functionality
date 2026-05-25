"""Tests for reminder UX helpers and list labels."""

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from src.bot.handlers.reminders import (
    _build_confirmation_text,
    _parse_time_on_date,
)
from src.bot.keyboards.builder import get_lists_list_keyboard
from src.db.models import RepeatRule, User
from src.repositories.user_repo import UserRepository
from src.utils.labels import repeat_rule_label
from src.worker.reminder_worker import ReminderWorkerService


def test_list_count_label_is_russian():
    """List buttons should not leak English implementation labels."""
    list_obj = SimpleNamespace(
        id=1,
        title="Случайно",
        items=[object(), object(), object()],
    )

    keyboard = get_lists_list_keyboard([list_obj])

    assert keyboard.inline_keyboard[0][0].text == "📋 Случайно (3 пункта)"


def test_parse_compact_time_on_selected_date_uses_user_timezone():
    """Users can type compact time without mandatory HH:MM format."""
    remind_at = _parse_time_on_date(
        "10",
        date(2026, 5, 25),
        "Europe/Moscow",
    )

    assert remind_at == datetime(2026, 5, 25, 7, 0, tzinfo=timezone.utc)


def test_parse_hhmm_time_on_selected_date():
    """Users can type 1030 as a quick time input."""
    remind_at = _parse_time_on_date(
        "1030",
        date(2026, 5, 25),
        "Europe/Moscow",
    )

    assert remind_at == datetime(2026, 5, 25, 7, 30, tzinfo=timezone.utc)


def test_parse_spaced_time_on_selected_date():
    """Users can type 10 30 as a quick time input."""
    remind_at = _parse_time_on_date(
        "10 30",
        date(2026, 5, 25),
        "Europe/Moscow",
    )

    assert remind_at == datetime(2026, 5, 25, 7, 30, tzinfo=timezone.utc)


def test_confirmation_text_uses_local_timezone_and_linked_list():
    """Confirmation should show local time and linked list context."""
    context = SimpleNamespace(
        user_data={
            "user_timezone": "Europe/Moscow",
            "linked_list_title": "Дела на завтра",
        }
    )

    text = _build_confirmation_text(
        context,
        datetime(2026, 5, 25, 7, 0, tzinfo=timezone.utc),
    )

    assert "📋 Список: Дела на завтра" in text
    assert "25.05.2026 10:00 (Europe/Moscow)" in text


def test_worker_displays_default_timezone_for_utc_user():
    """Worker notifications should not show UTC when project default is Moscow."""
    worker = ReminderWorkerService(bot=object())
    reminder = SimpleNamespace(
        title=None,
        text="Test",
        remind_at_utc=datetime(2026, 5, 23, 6, 6, tzinfo=timezone.utc),
        repeat_rule=RepeatRule.NONE,
        list_id=None,
        user=SimpleNamespace(timezone="UTC"),
    )

    message = worker._format_reminder_message(reminder)

    assert "23.05.2026 09:06 (Europe/Moscow)" in message


def test_repeat_rule_label_is_russian():
    """User-facing repeat labels should not leak enum values."""
    assert repeat_rule_label(RepeatRule.DAILY) == "ежедневно"
    assert repeat_rule_label("weekly") == "еженедельно"


def test_worker_uses_russian_repeat_label():
    """Reminder notifications should show localized repeat labels."""
    worker = ReminderWorkerService(bot=object())
    reminder = SimpleNamespace(
        title="Test",
        text="Body",
        remind_at_utc=datetime(2026, 5, 25, 7, 0, tzinfo=timezone.utc),
        repeat_rule=RepeatRule.DAILY,
        list_id=None,
        medication_id=None,
        user=SimpleNamespace(timezone="Europe/Moscow"),
    )

    message = worker._format_reminder_message(reminder)

    assert "Повтор: ежедневно" in message
    assert "Повтор: daily" not in message


@pytest.mark.asyncio
async def test_user_repo_uses_configured_default_timezone(db_session):
    """New and legacy UTC users should use the configured default timezone."""
    repo = UserRepository(db_session)

    user = await repo.get_or_create(telegram_id=5001)
    legacy = User(telegram_id=5002, timezone="UTC")
    db_session.add(legacy)
    await db_session.flush()

    normalized = await repo.get_or_create(telegram_id=5002)

    assert user.timezone == "Europe/Moscow"
    assert normalized.timezone == "Europe/Moscow"
