"""Tests for reminder notification delivery plan data model."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.db.models import (
    Reminder,
    ReminderNotification,
    ReminderNotificationStatus,
    ReminderStatus,
    RepeatRule,
    User,
)
from src.repositories.reminder_repo import ReminderRepository


@pytest.mark.asyncio
async def test_reminder_has_ordered_notification_plan(db_session):
    """A reminder event can own several scheduled delivery rows."""
    user = User(telegram_id=901001, timezone="Europe/Moscow")
    event_at = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
    reminder = Reminder(
        user=user,
        text="Проверить документы",
        remind_at_utc=event_at,
        repeat_rule=RepeatRule.NONE,
        status=ReminderStatus.ACTIVE,
    )
    reminder.notifications.extend(
        [
            ReminderNotification(
                notify_at_utc=event_at,
                offset_minutes=0,
            ),
            ReminderNotification(
                notify_at_utc=event_at - timedelta(hours=1),
                offset_minutes=60,
            ),
            ReminderNotification(
                notify_at_utc=event_at - timedelta(days=1),
                offset_minutes=1440,
            ),
        ]
    )
    db_session.add(reminder)
    await db_session.flush()
    reminder_id = reminder.id
    db_session.expunge_all()

    result = await db_session.execute(
        select(Reminder)
        .options(selectinload(Reminder.notifications))
        .where(Reminder.id == reminder_id)
    )
    saved = result.scalar_one()

    assert [item.offset_minutes for item in saved.notifications] == [1440, 60, 0]
    assert {item.status for item in saved.notifications} == {ReminderNotificationStatus.PENDING}


@pytest.mark.asyncio
async def test_reminder_delete_cascades_notification_plan(db_session):
    """Deleting a reminder should remove its delivery plan rows."""
    user = User(telegram_id=901002, timezone="Europe/Moscow")
    reminder = Reminder(
        user=user,
        text="Одноразовое напоминание",
        remind_at_utc=datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc),
        repeat_rule=RepeatRule.NONE,
        status=ReminderStatus.ACTIVE,
        notifications=[
            ReminderNotification(
                notify_at_utc=datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc),
                offset_minutes=0,
            )
        ],
    )
    db_session.add(reminder)
    await db_session.flush()
    notification_id = reminder.notifications[0].id

    await db_session.delete(reminder)
    await db_session.flush()

    result = await db_session.execute(
        select(ReminderNotification).where(ReminderNotification.id == notification_id)
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_reminder_repository_claims_due_notification_rows(db_session):
    """Worker repository should claim due delivery rows, not whole reminders."""
    user = User(telegram_id=901003, timezone="Europe/Moscow")
    now = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
    active = Reminder(
        user=user,
        text="Active event",
        remind_at_utc=now + timedelta(hours=1),
        repeat_rule=RepeatRule.NONE,
        status=ReminderStatus.ACTIVE,
        notifications=[
            ReminderNotification(
                notify_at_utc=now,
                offset_minutes=60,
                status=ReminderNotificationStatus.PENDING,
            ),
            ReminderNotification(
                notify_at_utc=now + timedelta(hours=1),
                offset_minutes=0,
                status=ReminderNotificationStatus.PENDING,
            ),
        ],
    )
    closed = Reminder(
        user=user,
        text="Closed event",
        remind_at_utc=now,
        repeat_rule=RepeatRule.NONE,
        status=ReminderStatus.DONE,
        notifications=[
            ReminderNotification(
                notify_at_utc=now,
                offset_minutes=0,
                status=ReminderNotificationStatus.PENDING,
            )
        ],
    )
    db_session.add_all([active, closed])
    await db_session.flush()
    due_id = active.notifications[0].id

    result = await ReminderRepository(db_session).get_due_notifications_locked(now, limit=10)

    assert [item.id for item in result] == [due_id]
    assert result[0].reminder.id == active.id
    assert result[0].reminder.user.telegram_id == 901003
    assert [item.offset_minutes for item in result[0].reminder.notifications] == [60, 0]


@pytest.mark.asyncio
async def test_create_next_occurrence_preserves_notification_offsets(db_session):
    """Recurring reminders should carry the same delivery plan to the next event."""
    user = User(telegram_id=901004, timezone="Europe/Moscow")
    event_at = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
    reminder = Reminder(
        user=user,
        text="Repeat event",
        remind_at_utc=event_at,
        repeat_rule=RepeatRule.DAILY,
        status=ReminderStatus.ACTIVE,
        notifications=[
            ReminderNotification(
                notify_at_utc=event_at - timedelta(days=1),
                offset_minutes=1440,
                status=ReminderNotificationStatus.SENT,
            ),
            ReminderNotification(
                notify_at_utc=event_at - timedelta(hours=1),
                offset_minutes=60,
                status=ReminderNotificationStatus.SENT,
            ),
            ReminderNotification(
                notify_at_utc=event_at,
                offset_minutes=0,
                status=ReminderNotificationStatus.SENT,
            ),
        ],
    )
    db_session.add(reminder)
    await db_session.flush()

    repo = ReminderRepository(db_session)
    next_reminder = await repo.create_next_occurrence(
        reminder,
        event_at + timedelta(days=1),
    )
    db_session.expunge_all()

    result = await db_session.execute(
        select(Reminder)
        .options(selectinload(Reminder.notifications))
        .where(Reminder.id == next_reminder.id)
    )
    saved = result.scalar_one()

    assert saved.remind_at_utc.replace(tzinfo=timezone.utc) == event_at + timedelta(days=1)
    assert [item.offset_minutes for item in saved.notifications] == [1440, 60, 0]
    assert {item.status for item in saved.notifications} == {ReminderNotificationStatus.PENDING}


def test_reminder_notification_migration_backfills_existing_reminders():
    """The migration should preserve legacy reminders as one notification each."""
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "019_reminder_notifications.py"
    )
    migration = migration_path.read_text(encoding="utf-8")

    assert "INSERT INTO reminder_notifications" in migration
    assert "FROM reminders" in migration
    assert "notified_at IS NOT NULL" in migration
    assert "'PENDING'" in migration
    assert "'SENT'" in migration
    assert "'CANCELED'" in migration
