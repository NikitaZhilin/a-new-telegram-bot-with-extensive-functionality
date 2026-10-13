"""Medication buttons must mark the dose they were sent for."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.bot.handlers.medications import _parse_slot
from src.db.models import RepeatRule, User
from src.services.medication_service import MedicationService
from src.worker.reminder_worker import ReminderWorkerService

MSK = timezone(timedelta(hours=3))
TZ = "Europe/Moscow"


def msk(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 3, day, hour, minute, tzinfo=MSK).astimezone(timezone.utc)


async def _twice_daily(db_session, telegram_id: int):
    user = User(telegram_id=telegram_id, timezone=TZ)
    db_session.add(user)
    await db_session.flush()
    service = MedicationService(db_session)
    medication = await service.create_medication(user_id=user.id, name="Magnesium")
    await service.replace_daily_reminders(
        medication_id=medication.id,
        user_id=user.id,
        remind_at_utcs=[msk(10, 9), msk(10, 21)],
    )
    return user, service, medication


def _daily_reminder(user, medication, slot_utc):
    return SimpleNamespace(
        id=1,
        user_id=user.id,
        medication_id=medication.id,
        medication=medication,
        repeat_rule=RepeatRule.DAILY,
        remind_at_utc=slot_utc,
        user=SimpleNamespace(telegram_id=user.telegram_id, timezone=TZ),
    )


@pytest.mark.asyncio
async def test_late_taken_on_evening_reminder_marks_evening_dose(db_session):
    """Pressing «Принял» on the 21:00 message at 07:30 must not close the 09:00 dose."""
    user, service, medication = await _twice_daily(db_session, 77001)

    intake, state = await service.mark_taken_for_slot(
        medication.id, user.id, TZ, slot_utc=msk(10, 21), taken_at_utc=msk(11, 7, 30)
    )

    assert intake is not None
    assert state.reason == "slot_already_marked"
    assert state.current_slot_at_utc == msk(10, 21)

    morning = await service.get_slot_action_state(medication.id, user.id, TZ, msk(11, 9), now_utc=msk(11, 9))
    assert morning.can_mark is True

    worker = ReminderWorkerService(bot=None)
    skipped = await worker._should_skip_medication_notification(
        db_session, _daily_reminder(user, medication, msk(11, 9)), msk(11, 9)
    )
    assert skipped is False, "the 09:00 reminder must still be sent"


@pytest.mark.asyncio
async def test_same_slot_cannot_be_marked_twice(db_session):
    user, service, medication = await _twice_daily(db_session, 77002)

    first, _ = await service.mark_taken_for_slot(medication.id, user.id, TZ, msk(10, 9), msk(10, 9, 5))
    second, state = await service.mark_taken_for_slot(medication.id, user.id, TZ, msk(10, 9), msk(10, 9, 6))

    assert first is not None
    assert second is None
    assert state.reason == "slot_already_marked"


@pytest.mark.asyncio
async def test_daily_reminder_skipped_when_its_own_slot_is_marked(db_session):
    user, service, medication = await _twice_daily(db_session, 77003)
    await service.mark_taken_for_current_slot(medication.id, user.id, TZ, taken_at_utc=msk(10, 8, 30))

    worker = ReminderWorkerService(bot=None)

    assert await worker._should_skip_medication_notification(
        db_session, _daily_reminder(user, medication, msk(10, 9)), msk(10, 9)
    ) is True
    assert await worker._should_skip_medication_notification(
        db_session, _daily_reminder(user, medication, msk(10, 21)), msk(10, 21)
    ) is False


@pytest.mark.asyncio
async def test_snoozed_reminder_is_dropped_after_dose_was_taken(db_session):
    """«Отложить 15 мин», then «Принял» 5 minutes later: no extra reminder."""
    user, service, medication = await _twice_daily(db_session, 77004)
    await service.mark_taken_for_current_slot(medication.id, user.id, TZ, taken_at_utc=msk(10, 9, 5))
    snoozed = SimpleNamespace(
        id=2,
        user_id=user.id,
        medication_id=medication.id,
        medication=medication,
        repeat_rule=RepeatRule.NONE,
        remind_at_utc=msk(10, 9, 15),
        user=SimpleNamespace(telegram_id=user.telegram_id, timezone=TZ),
    )

    worker = ReminderWorkerService(bot=None)

    assert await worker._should_skip_medication_notification(db_session, snoozed, msk(10, 9, 15)) is True


@pytest.mark.asyncio
async def test_old_slot_press_falls_back_to_current_slot(db_session):
    """A button older than a day behaves like before: it marks the current dose."""
    user, service, medication = await _twice_daily(db_session, 77005)

    intake, state = await service.mark_taken_for_slot(
        medication.id, user.id, TZ, slot_utc=msk(10, 9), taken_at_utc=msk(12, 9, 10)
    )

    assert intake is not None
    assert state.current_slot_at_utc == msk(12, 9)


def test_daily_medication_buttons_carry_their_slot():
    worker = ReminderWorkerService(bot=None)
    reminder = SimpleNamespace(
        medication_id=77,
        medication=SimpleNamespace(id=77, name="Vitamin D"),
        repeat_rule=RepeatRule.DAILY,
        remind_at_utc=msk(10, 21),
    )

    markup = worker._build_reminder_reply_markup(reminder)

    taken = markup.inline_keyboard[0][0].callback_data
    skipped = markup.inline_keyboard[1][0].callback_data
    assert taken.startswith("med_taken:77:")
    assert skipped.startswith("med_skip:77:")
    assert _parse_slot(taken) == msk(10, 21)
    assert len(taken.encode()) <= 64
    assert _parse_slot("med_taken:77") is None
