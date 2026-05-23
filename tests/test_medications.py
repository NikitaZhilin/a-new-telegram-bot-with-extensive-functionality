"""Medication service tests."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from src.db.models import MedicationIntakeStatus, Reminder, ReminderStatus, RepeatRule, User
from src.bot.handlers.medications import _normalize_hhmm, _parse_local_time_list
from src.services.medication_service import MedicationService


@pytest.mark.asyncio
async def test_medication_service_keeps_ownership(db_session):
    """Users must not view, mark, or remind medications owned by others."""
    user = User(telegram_id=6001, timezone="Europe/Moscow")
    other_user = User(telegram_id=6002, timezone="Europe/Moscow")
    db_session.add_all([user, other_user])
    await db_session.flush()

    service = MedicationService(db_session)
    medication = await service.create_medication(
        user_id=user.id,
        name="Vitamin D",
        dosage="1 tablet",
        instructions="after breakfast",
    )

    assert await service.get_medication(medication.id, other_user.id) is None
    assert await service.mark_taken(medication.id, other_user.id) is None
    assert await service.create_reminder(
        medication_id=medication.id,
        user_id=other_user.id,
        remind_at_utc=datetime(2026, 5, 23, 7, 0, tzinfo=timezone.utc),
    ) is None

    intake = await service.mark_taken(medication.id, user.id)
    assert intake is not None
    assert intake.medication_id == medication.id


@pytest.mark.asyncio
async def test_medication_reminder_links_to_medication(db_session):
    """Medication reminders should carry medication_id and default to daily repeat."""
    user = User(telegram_id=6003, timezone="Europe/Moscow")
    db_session.add(user)
    await db_session.flush()

    service = MedicationService(db_session)
    medication = await service.create_medication(
        user_id=user.id,
        name="Antibiotic",
        dosage="500 mg",
        importance="important",
    )

    reminder = await service.create_reminder(
        medication_id=medication.id,
        user_id=user.id,
        remind_at_utc=datetime(2026, 5, 23, 7, 0, tzinfo=timezone.utc),
    )

    assert reminder is not None
    assert reminder.medication_id == medication.id
    assert reminder.repeat_rule == RepeatRule.DAILY
    assert "Antibiotic" in reminder.text
    assert "500 mg" in reminder.text
    assert "Важное напоминание" in reminder.text


@pytest.mark.asyncio
async def test_medication_create_reminder_deduplicates_same_daily_time(db_session):
    """Creating the same daily medication time twice should not duplicate notifications."""
    user = User(telegram_id=6009, timezone="Europe/Moscow")
    db_session.add(user)
    await db_session.flush()

    service = MedicationService(db_session)
    medication = await service.create_medication(user_id=user.id, name="Magnesium")

    first = await service.create_reminder(
        medication_id=medication.id,
        user_id=user.id,
        remind_at_utc=datetime(2026, 5, 23, 6, 0, tzinfo=timezone.utc),
    )
    second = await service.create_reminder(
        medication_id=medication.id,
        user_id=user.id,
        remind_at_utc=datetime(2026, 5, 24, 6, 0, tzinfo=timezone.utc),
    )
    result = await db_session.execute(
        select(Reminder).where(
            Reminder.medication_id == medication.id,
            Reminder.status == ReminderStatus.ACTIVE,
            Reminder.repeat_rule == RepeatRule.DAILY,
        )
    )

    active_reminders = result.scalars().all()
    assert first is not None
    assert second is not None
    assert second.id == first.id
    assert len(active_reminders) == 1


@pytest.mark.asyncio
async def test_medication_replace_daily_reminders_cancels_removed_times(db_session):
    """Updating a medication schedule should replace old active times."""
    user = User(telegram_id=6010, timezone="Europe/Moscow")
    db_session.add(user)
    await db_session.flush()

    service = MedicationService(db_session)
    medication = await service.create_medication(user_id=user.id, name="Magnesium")
    await service.replace_daily_reminders(
        medication_id=medication.id,
        user_id=user.id,
        remind_at_utcs=[
            datetime(2026, 5, 23, 6, 0, tzinfo=timezone.utc),
            datetime(2026, 5, 23, 18, 0, tzinfo=timezone.utc),
        ],
    )
    updated = await service.replace_daily_reminders(
        medication_id=medication.id,
        user_id=user.id,
        remind_at_utcs=[datetime(2026, 5, 24, 18, 0, tzinfo=timezone.utc)],
    )

    result = await db_session.execute(
        select(Reminder).where(Reminder.medication_id == medication.id)
    )
    reminders = result.scalars().all()
    active = [item for item in reminders if item.status == ReminderStatus.ACTIVE]
    canceled = [item for item in reminders if item.status == ReminderStatus.CANCELED]

    assert len(updated) == 1
    assert len(active) == 1
    assert active[0].remind_at_utc == datetime(2026, 5, 24, 18, 0, tzinfo=timezone.utc)
    assert len(canceled) == 1


@pytest.mark.asyncio
async def test_medication_importance_defaults_and_validation(db_session):
    """Medication importance should be stored safely with a conservative default."""
    user = User(telegram_id=6006, timezone="Europe/Moscow")
    db_session.add(user)
    await db_session.flush()

    service = MedicationService(db_session)
    supplement = await service.create_medication(
        user_id=user.id,
        name="Vitamin C",
        importance="supplement",
    )
    fallback = await service.create_medication(
        user_id=user.id,
        name="Unknown",
        importance="wrong",
    )

    assert supplement.importance == "supplement"
    assert fallback.importance == "normal"


def test_medication_frequency_time_parser():
    """Medication frequency flow should require exact user-provided times."""
    assert _normalize_hhmm("9") == "0900"
    assert _normalize_hhmm("09:30") == "0930"
    assert _normalize_hhmm("930") == "0930"

    parsed = _parse_local_time_list("09:00, 21:30", 2, "Europe/Moscow")

    assert len(parsed) == 2
    assert all(item.tzinfo is not None for item in parsed)

    with pytest.raises(ValueError):
        _parse_local_time_list("09:00", 2, "Europe/Moscow")

    with pytest.raises(ValueError):
        _parse_local_time_list("09:00, 09:00", 2, "Europe/Moscow")


@pytest.mark.asyncio
async def test_archiving_medication_cancels_active_medication_reminders(db_session):
    """Archived medications should stop future reminder notifications."""
    user = User(telegram_id=6004, timezone="Europe/Moscow")
    db_session.add(user)
    await db_session.flush()

    service = MedicationService(db_session)
    medication = await service.create_medication(user_id=user.id, name="Evening pill")
    reminder = await service.create_reminder(
        medication_id=medication.id,
        user_id=user.id,
        remind_at_utc=datetime(2026, 5, 23, 18, 0, tzinfo=timezone.utc),
    )

    archived = await service.archive_medication(medication.id, user.id)

    assert archived is True
    assert reminder.status == ReminderStatus.CANCELED


@pytest.mark.asyncio
async def test_medication_skip_and_snooze(db_session):
    """Medication flow should support skipped marks and one-time snooze reminders."""
    user = User(telegram_id=6005, timezone="Europe/Moscow")
    db_session.add(user)
    await db_session.flush()

    service = MedicationService(db_session)
    medication = await service.create_medication(user_id=user.id, name="Drops")

    skipped = await service.mark_skipped(medication.id, user.id)
    snooze = await service.snooze_reminder(medication.id, user.id, minutes=15)

    assert skipped is not None
    assert skipped.status == MedicationIntakeStatus.SKIPPED
    assert snooze is not None
    assert snooze.repeat_rule == RepeatRule.NONE
    assert snooze.medication_id == medication.id


@pytest.mark.asyncio
async def test_medication_once_daily_mark_hides_until_next_day_window(db_session):
    """A once-daily medication should not be marked twice before tomorrow's window."""
    user = User(telegram_id=6007, timezone="Europe/Moscow")
    db_session.add(user)
    await db_session.flush()

    service = MedicationService(db_session)
    medication = await service.create_medication(user_id=user.id, name="L-thyroxine")
    await service.create_reminder(
        medication_id=medication.id,
        user_id=user.id,
        remind_at_utc=datetime(2026, 5, 23, 6, 0, tzinfo=timezone.utc),  # 09:00 Moscow
    )

    taken_at = datetime(2026, 5, 23, 5, 30, tzinfo=timezone.utc)  # 08:30 Moscow
    intake, state_after = await service.mark_taken_for_current_slot(
        medication.id,
        user.id,
        "Europe/Moscow",
        taken_at_utc=taken_at,
    )

    assert intake is not None
    assert state_after.can_mark is False
    assert state_after.next_available_at_utc == datetime(2026, 5, 24, 4, 0, tzinfo=timezone.utc)

    before_next_window = await service.get_intake_action_state(
        medication.id,
        user.id,
        "Europe/Moscow",
        now_utc=datetime(2026, 5, 24, 3, 59, tzinfo=timezone.utc),
    )
    next_window = await service.get_intake_action_state(
        medication.id,
        user.id,
        "Europe/Moscow",
        now_utc=datetime(2026, 5, 24, 4, 0, tzinfo=timezone.utc),
    )

    assert before_next_window.can_mark is False
    assert next_window.can_mark is True


@pytest.mark.asyncio
async def test_medication_two_daily_marks_reopen_before_next_slot(db_session):
    """A twice-daily medication should reopen two hours before the next scheduled time."""
    user = User(telegram_id=6008, timezone="Europe/Moscow")
    db_session.add(user)
    await db_session.flush()

    service = MedicationService(db_session)
    medication = await service.create_medication(user_id=user.id, name="Magnesium")
    await service.create_reminder(
        medication_id=medication.id,
        user_id=user.id,
        remind_at_utc=datetime(2026, 5, 23, 6, 0, tzinfo=timezone.utc),  # 09:00 Moscow
    )
    await service.create_reminder(
        medication_id=medication.id,
        user_id=user.id,
        remind_at_utc=datetime(2026, 5, 23, 18, 0, tzinfo=timezone.utc),  # 21:00 Moscow
    )

    intake, state_after = await service.mark_taken_for_current_slot(
        medication.id,
        user.id,
        "Europe/Moscow",
        taken_at_utc=datetime(2026, 5, 23, 6, 30, tzinfo=timezone.utc),  # 09:30 Moscow
    )
    stale_intake, stale_state = await service.mark_taken_for_current_slot(
        medication.id,
        user.id,
        "Europe/Moscow",
        taken_at_utc=datetime(2026, 5, 23, 15, 59, tzinfo=timezone.utc),  # 18:59 Moscow
    )
    next_slot_state = await service.get_intake_action_state(
        medication.id,
        user.id,
        "Europe/Moscow",
        now_utc=datetime(2026, 5, 23, 16, 0, tzinfo=timezone.utc),  # 19:00 Moscow
    )

    assert intake is not None
    assert state_after.can_mark is False
    assert state_after.next_available_at_utc == datetime(2026, 5, 23, 16, 0, tzinfo=timezone.utc)
    assert stale_intake is None
    assert stale_state.can_mark is False
    assert next_slot_state.can_mark is True
