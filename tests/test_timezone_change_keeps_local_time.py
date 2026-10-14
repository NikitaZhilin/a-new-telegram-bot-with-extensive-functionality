"""Changing the timezone keeps reminders on the same local clock time."""

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from src.db.models import ReminderNotificationStatus, RepeatRule, User
from src.services.medication_service import MedicationService
from src.services.reminder_service import ReminderService
from src.services.settings_service import SettingsService

MOSCOW = ZoneInfo("Europe/Moscow")
TOKYO = ZoneInfo("Asia/Tokyo")  # no DST: stable expectations


def _local_tomorrow(tz, hour, days=1):
    day = datetime.now(tz).date() + timedelta(days=days)
    return datetime.combine(day, time(hour, 0), tzinfo=tz)


async def _user(db_session, telegram_id):
    user = User(telegram_id=telegram_id, timezone="Europe/Moscow")
    db_session.add(user)
    await db_session.flush()
    return user


def _as_utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@pytest.mark.asyncio
async def test_daily_reminder_stays_at_nine_after_moving_to_tokyo(db_session):
    """Before: 09:00 Moscow became 15:00 in Tokyo (same moment, other clock)."""
    user = await _user(db_session, 83001)
    service = ReminderService(db_session)
    nine_moscow = _local_tomorrow(MOSCOW, 9, days=2)
    reminder = await service.create_reminder(
        user_id=user.id, text="Зарядка", remind_at_utc=nine_moscow.astimezone(timezone.utc),
        repeat_rule=RepeatRule.DAILY, notify_offsets_minutes=[15],
    )

    moved = await SettingsService(db_session).apply_timezone(user, "asia/tokyo")

    assert user.timezone == "Asia/Tokyo"
    assert moved == 1
    reloaded = await service.get_reminder(reminder.id, user.id)
    local = _as_utc(reloaded.remind_at_utc).astimezone(TOKYO)
    assert (local.date(), local.hour, local.minute) == (nine_moscow.date(), 9, 0)
    pending = [n for n in reloaded.notifications if n.status == ReminderNotificationStatus.PENDING]
    assert sorted(n.offset_minutes for n in pending) == [0, 15]
    for notification in pending:
        expected = _as_utc(reloaded.remind_at_utc) - timedelta(minutes=notification.offset_minutes)
        assert _as_utc(notification.notify_at_utc) == expected


@pytest.mark.asyncio
async def test_medication_schedule_keeps_local_times(db_session):
    user = await _user(db_session, 83002)
    meds = MedicationService(db_session)
    medication = await meds.create_medication(user_id=user.id, name="Магний")
    await meds.replace_daily_reminders(
        medication_id=medication.id,
        user_id=user.id,
        remind_at_utcs=[
            _local_tomorrow(MOSCOW, 9).astimezone(timezone.utc),
            _local_tomorrow(MOSCOW, 21).astimezone(timezone.utc),
        ],
    )

    await SettingsService(db_session).apply_timezone(user, "Asia/Tokyo")

    times = await meds._get_daily_schedule_times(medication.id, user.id, "Asia/Tokyo")
    assert times == [time(9, 0), time(21, 0)]


@pytest.mark.asyncio
async def test_one_time_reminder_that_would_land_in_the_past_is_kept(db_session):
    """Moving east can put a one-time reminder in the past; it must not fire at once."""
    user = await _user(db_session, 83003)
    service = ReminderService(db_session)
    soon = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=1)
    reminder = await service.create_reminder(user_id=user.id, text="Звонок", remind_at_utc=soon)

    await SettingsService(db_session).apply_timezone(user, "Asia/Tokyo")

    reloaded = await service.get_reminder(reminder.id, user.id)
    assert _as_utc(reloaded.remind_at_utc) == soon


@pytest.mark.asyncio
async def test_same_timezone_changes_nothing(db_session):
    user = await _user(db_session, 83004)
    service = ReminderService(db_session)
    await service.create_reminder(
        user_id=user.id, text="x", remind_at_utc=_local_tomorrow(MOSCOW, 9).astimezone(timezone.utc)
    )

    assert await SettingsService(db_session).apply_timezone(user, "Europe/Moscow") == 0


@pytest.mark.asyncio
async def test_driver_document_reminders_are_not_moved(db_session):
    from src.services.driver_service import DriverService

    user = await _user(db_session, 83005)
    driver = DriverService(db_session)
    expires = datetime.now(timezone.utc) + timedelta(days=60)
    document = await driver.create_document(
        user_id=user.id, title="ОСАГО", document_type="insurance",
        expires_at_utc=expires, remind_before_days=30,
    )
    reminder_service = ReminderService(db_session)
    before, _ = await reminder_service.get_reminders_list(user.id, source_module="driver")
    assert before and before[0].driver_document_id == document.id
    before_at = _as_utc(before[0].remind_at_utc)

    await SettingsService(db_session).apply_timezone(user, "Asia/Tokyo")

    after = await reminder_service.get_reminder(before[0].id, user.id)
    assert _as_utc(after.remind_at_utc) == before_at
