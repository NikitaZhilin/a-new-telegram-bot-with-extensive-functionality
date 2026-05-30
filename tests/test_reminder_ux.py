"""Tests for reminder UX helpers and list labels."""

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from src.bot.handlers.reminders import (
    _build_confirmation_text,
    _format_notify_offsets,
    _looks_like_full_datetime,
    _parse_flexible_datetime,
    _parse_notify_offsets_callback,
    _parse_time_on_date,
)
from src.bot.keyboards.builder import (
    get_lists_list_keyboard,
    get_reminder_edit_keyboard,
    get_reminder_notify_offsets_keyboard,
    get_reminder_view_keyboard,
)
from src.db.models import RepeatRule, User
from src.repositories.user_repo import UserRepository
from src.utils.date_parser import parse_datetime
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


def test_parse_dot_and_comma_time_on_selected_date():
    """Users can use dot or comma as separators in quick time input."""
    selected_date = date(2026, 5, 25)

    assert _parse_time_on_date("10.30", selected_date, "Europe/Moscow") == datetime(
        2026,
        5,
        25,
        7,
        30,
        tzinfo=timezone.utc,
    )
    assert _parse_time_on_date("15,00", selected_date, "Europe/Moscow") == datetime(
        2026,
        5,
        25,
        12,
        0,
        tzinfo=timezone.utc,
    )


def test_parse_daypart_time_on_selected_date():
    """Users can type daypart words instead of strict HH:MM."""
    remind_at = _parse_time_on_date(
        "вечером",
        date(2026, 5, 25),
        "Europe/Moscow",
    )

    assert remind_at == datetime(2026, 5, 25, 16, 0, tzinfo=timezone.utc)


def test_full_datetime_detection_accepts_friendly_phrases():
    """Date input should skip the separate time step when the phrase has time intent."""
    assert _looks_like_full_datetime("послезавтра вечером") is True
    assert _looks_like_full_datetime("28 мая 15") is True
    assert _looks_like_full_datetime("25.12 вечером") is True
    assert _looks_like_full_datetime("28 мая") is False


def test_parse_month_name_datetime_with_short_hour():
    """Month-name phrases should parse without requiring strict HH:MM format."""
    context = SimpleNamespace(user_data={"user_timezone": "Europe/Moscow"})

    remind_at = _parse_flexible_datetime("31 декабря 2026 15", context)

    assert remind_at == datetime(2026, 12, 31, 12, 0, tzinfo=timezone.utc)


def test_parse_datetime_month_name_returns_local_timezone():
    """Shared parser should support Russian month names and short time."""
    parsed = parse_datetime("31 декабря 2026 15", "Europe/Moscow")

    assert parsed.isoformat() == "2026-12-31T15:00:00+03:00"


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


def test_notification_offsets_always_include_final_delivery():
    """Advance notification choices should keep the main event notification."""
    assert _parse_notify_offsets_callback("rem_notify:1440,60") == [1440, 60, 0]
    assert _parse_notify_offsets_callback("rem_notify:0") == [0]
    assert _format_notify_offsets([1440, 60]) == "за сутки, за 1 час, в выбранное время"


def test_reminder_notify_offsets_keyboard_exposes_presets_and_repeat():
    """Creation flow should select delivery plan without a separate confirmation step."""
    keyboard = get_reminder_notify_offsets_keyboard("weekly")
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    texts = [button.text for row in keyboard.inline_keyboard for button in row]

    assert "rem_notify:0" in callbacks
    assert "rem_notify:1440,120,60" in callbacks
    assert "rem_repeat_set" in callbacks
    assert "rem_time_change" in callbacks
    assert "🔁 Повтор: еженедельно" in texts


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


def test_reminder_view_keyboard_uses_compact_edit_and_next_action():
    """Active reminder view should not show duplicate cancel/delete actions."""
    keyboard = get_reminder_view_keyboard(10, status="active")
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    texts = [button.text for row in keyboard.inline_keyboard for button in row]

    assert "reminder_edit_menu:10" in callbacks
    assert "reminder_create" in callbacks
    assert "reminder_cancel:10" not in callbacks
    assert "reminder_edit_text:10" not in callbacks
    assert "✏️ Изменить" in texts
    assert "➕ Следующее напоминание" in texts


def test_reminder_view_keyboard_can_hide_done_action_before_due_window():
    """The done action should not be visible right after creating a future reminder."""
    keyboard = get_reminder_view_keyboard(10, status="active", can_complete=False)
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]

    assert "reminder_done:10" not in callbacks
    assert "reminder_edit_menu:10" in callbacks


def test_reminder_edit_keyboard_exposes_edit_choices():
    """Compact edit button should open all reminder edit choices."""
    keyboard = get_reminder_edit_keyboard(10)
    callbacks = {
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
    }

    assert callbacks == {
        "reminder_edit_text:10",
        "reminder_edit_time:10",
        "reminder_edit_repeat:10",
        "reminder_view:10",
    }


def test_driver_reminder_view_does_not_start_general_next_reminder():
    """Driver reminders should not lead into the general reminder flow."""
    keyboard = get_reminder_view_keyboard(10, status="active", source_module="driver")
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]

    assert "reminder_create" not in callbacks
    assert "reminder_edit_menu:10" in callbacks
