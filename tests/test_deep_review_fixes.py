"""Scenarios from the deep review: reminders that could not be stopped,
"done" that killed a repeating series, stale wizards eating menu buttons."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from telegram import Chat, Message, Update
from telegram import User as TgUser
from telegram.ext import CommandHandler, ConversationHandler

from src.bot.app import create_application
from src.bot.handlers.conversation_exit import MAIN_MENU_LABELS, TEXT_INPUT
from src.bot.keyboards import get_main_menu_keyboard
from src.db.models import (
    Reminder,
    ReminderNotificationStatus,
    ReminderStatus,
    RepeatRule,
    User,
)
from src.services.list_service import ListService
from src.services.medication_service import MedicationService
from src.services.note_service import NoteService
from src.services.reminder_service import ReminderService


def _future(hours=2):
    return datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=hours)


async def _user(db_session, telegram_id, tz="Europe/Moscow"):
    user = User(telegram_id=telegram_id, timezone=tz)
    db_session.add(user)
    await db_session.flush()
    return user


async def _reminders(db_session, user_id):
    result = await db_session.execute(
        select(Reminder).where(Reminder.user_id == user_id).order_by(Reminder.id)
    )
    return list(result.scalars().all())


# --- "Done" on a repeating reminder -------------------------------------------------

@pytest.mark.asyncio
async def test_done_on_daily_reminder_keeps_the_series(db_session):
    """Before: «Выполнено» on today's daily reminder stopped it forever."""
    user = await _user(db_session, 81001)
    service = ReminderService(db_session)
    first_at = _future(1)
    reminder = await service.create_reminder(
        user_id=user.id, text="Зарядка", remind_at_utc=first_at,
        repeat_rule=RepeatRule.DAILY, notify_offsets_minutes=[15],
    )

    await service.mark_reminder_done(reminder.id, user.id)

    rows = await _reminders(db_session, user.id)
    assert [row.status for row in rows] == [ReminderStatus.DONE, ReminderStatus.ACTIVE]
    nxt = rows[1]
    assert nxt.remind_at_utc.replace(tzinfo=timezone.utc) == first_at + timedelta(days=1)
    nxt = await service.get_reminder(nxt.id, user.id)
    pending = sorted(n.offset_minutes for n in nxt.notifications if n.status == ReminderNotificationStatus.PENDING)
    assert pending == [0, 15]


@pytest.mark.asyncio
async def test_done_on_one_time_reminder_creates_nothing(db_session):
    user = await _user(db_session, 81002)
    service = ReminderService(db_session)
    reminder = await service.create_reminder(user_id=user.id, text="Позвонить", remind_at_utc=_future())

    await service.mark_reminder_done(reminder.id, user.id)

    assert len(await _reminders(db_session, user.id)) == 1


# --- Editing a finished reminder ----------------------------------------------------

@pytest.mark.asyncio
async def test_new_time_for_finished_reminder_reactivates_it(db_session):
    """Before (web): the time changed but the reminder stayed «выполнено» and never came."""
    user = await _user(db_session, 81003)
    service = ReminderService(db_session)
    reminder = await service.create_reminder(user_id=user.id, text="Купить хлеб", remind_at_utc=_future())
    await service.mark_reminder_done(reminder.id, user.id)

    updated = await service.update_reminder_time(reminder.id, user.id, _future(5))

    assert updated.status == ReminderStatus.ACTIVE
    assert any(n.status == ReminderNotificationStatus.PENDING for n in updated.notifications)


@pytest.mark.asyncio
async def test_moving_reminder_keeps_early_notice_already_sent(db_session):
    user = await _user(db_session, 81004)
    service = ReminderService(db_session)
    reminder = await service.create_reminder(
        user_id=user.id, text="Врач", remind_at_utc=_future(3), notify_offsets_minutes=[1440, 0]
    )
    early = next(n for n in reminder.notifications if n.offset_minutes == 1440)
    early.status = ReminderNotificationStatus.SENT
    await db_session.flush()

    moved = await service.update_reminder_time(reminder.id, user.id, _future(48))

    pending = sorted(n.offset_minutes for n in moved.notifications if n.status == ReminderNotificationStatus.PENDING)
    assert pending == [0, 1440]


# --- Reminders that could not be found or stopped ------------------------------------

@pytest.mark.asyncio
async def test_bot_reminder_list_shows_list_note_and_driver_reminders(db_session):
    user = await _user(db_session, 81005)
    service = ReminderService(db_session)
    todo = await ListService(db_session).create_list(user.id, "Покупки")
    note = await NoteService(db_session).create_note(user.id, "Рецепт", "текст")
    medication = await MedicationService(db_session).create_medication(user_id=user.id, name="Магний")
    for kwargs in (
        {"text": "general"},
        {"text": "list", "list_id": todo.id},
        {"text": "note", "note_id": note.id},
        {"text": "driver", "source_module": "driver"},
        {"text": "med", "medication_id": medication.id},
    ):
        await service.create_reminder(user_id=user.id, remind_at_utc=_future(), **kwargs)

    shown, total = await service.get_reminders_list(
        user.id, source_module=None, exclude_source_modules=("medication",)
    )

    assert total == 4
    assert {item.text for item in shown} == {"general", "list", "note", "driver"}


@pytest.mark.asyncio
async def test_deleting_list_cancels_its_reminders(db_session):
    user = await _user(db_session, 81006)
    todo = await ListService(db_session).create_list(user.id, "Дача")
    service = ReminderService(db_session)
    reminder = await service.create_reminder(
        user_id=user.id, text="Напомнить про список", remind_at_utc=_future(), list_id=todo.id,
        repeat_rule=RepeatRule.WEEKLY,
    )
    reminder_id = reminder.id

    assert await ListService(db_session).delete_list(todo.id, user.id) is True

    reloaded = await service.get_reminder(reminder_id, user.id)
    assert reloaded.status == ReminderStatus.CANCELED
    assert all(n.status != ReminderNotificationStatus.PENDING for n in reloaded.notifications)


@pytest.mark.asyncio
async def test_archiving_note_cancels_its_reminders(db_session):
    user = await _user(db_session, 81007)
    note = await NoteService(db_session).create_note(user.id, "Паспорт", "продлить")
    service = ReminderService(db_session)
    reminder = await service.create_reminder(
        user_id=user.id, text="Напомнить про заметку", remind_at_utc=_future(), note_id=note.id
    )

    assert await NoteService(db_session).archive_note(note.id, user.id) is True

    assert (await service.get_reminder(reminder.id, user.id)).status == ReminderStatus.CANCELED


# --- Medication edits ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_medication_dosage_change_updates_reminder_text(db_session):
    """Before: reminders kept showing the old dosage after it was changed."""
    user = await _user(db_session, 81008)
    service = MedicationService(db_session)
    medication = await service.create_medication(user_id=user.id, name="Магний", dosage="1 таблетка")
    reminder = await service.create_reminder(medication.id, user.id, _future())
    assert "1 таблетка" in reminder.text

    await service.update_medication(medication.id, user.id, dosage="2 таблетки")

    await db_session.refresh(reminder)
    assert "2 таблетки" in reminder.text
    assert "1 таблетка" not in reminder.text


# --- Wizards and the main menu ---------------------------------------------------------

def _text_update(text: str) -> Update:
    user = TgUser(id=1, first_name="T", is_bot=False)
    message = Message(
        message_id=1,
        date=datetime.now(timezone.utc),
        chat=Chat(id=1, type="private"),
        from_user=user,
        text=text,
    )
    return Update(update_id=1, message=message)


def test_wizard_text_input_ignores_main_menu_buttons():
    keyboard_labels = {button.text for row in get_main_menu_keyboard().keyboard for button in row}
    assert keyboard_labels <= set(MAIN_MENU_LABELS), "every menu button must be known to wizards"

    for label in keyboard_labels:
        assert not TEXT_INPUT.check_update(_text_update(label)), label
    assert TEXT_INPUT.check_update(_text_update("Купить молоко"))


def test_every_wizard_can_be_left_and_times_out():
    app = create_application()
    group = app.handlers[0]
    conversations = [handler for handler in group if isinstance(handler, ConversationHandler)]
    assert conversations

    for conv in conversations:
        assert conv.conversation_timeout, conv.name
        commands = {
            command
            for handler in conv.fallbacks
            if isinstance(handler, CommandHandler)
            for command in handler.commands
        }
        assert "start" in commands and "cancel" in commands

    start_index = next(
        index for index, handler in enumerate(group)
        if isinstance(handler, CommandHandler) and "start" in handler.commands
    )
    last_conversation_index = max(group.index(conv) for conv in conversations)
    assert start_index > last_conversation_index, "/start must reach an open wizard first"


# --- Web reminder list -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_web_reminders_show_active_first_even_with_long_history(db_session):
    """Before: 60 old DONE rows of a daily reminder filled the 50-item list."""
    import httpx

    from src.api.app import create_application as create_api
    from src.db.session import get_db
    from tests.test_user_api import _telegram_init_data

    user = await _user(db_session, 81009)
    old = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    for day in range(60):
        db_session.add(Reminder(
            user_id=user.id, text=f"old {day}", remind_at_utc=old + timedelta(days=day),
            repeat_rule=RepeatRule.DAILY, status=ReminderStatus.DONE, source_module="general",
        ))
    db_session.add(Reminder(
        user_id=user.id, text="active driver", remind_at_utc=_future(),
        repeat_rule=RepeatRule.DAILY, status=ReminderStatus.ACTIVE, source_module="driver",
    ))
    await db_session.commit()

    app = create_api()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    headers = {"X-Telegram-Init-Data": _telegram_init_data({"id": 81009, "first_name": "T"})}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/me/reminders?active_only=false", headers=headers)

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 50
    assert items[0]["text"] == "active driver"
    assert items[1]["text"] == "old 59", "history newest first"
