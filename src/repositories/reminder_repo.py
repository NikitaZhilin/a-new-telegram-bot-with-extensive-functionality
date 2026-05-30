"""Reminder repository with atomic operations for worker."""

import calendar
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models import (
    Reminder,
    ReminderNotification,
    ReminderNotificationStatus,
    ReminderStatus,
    RepeatRule,
    User,
)
from src.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class ReminderRepository(BaseRepository[Reminder]):
    """
    Repository for Reminder model with atomic operations.
    
    Uses SELECT ... FOR UPDATE SKIP LOCKED for safe concurrent access
    when scaling to multiple worker instances.
    """

    def __init__(self, db: AsyncSession):
        super().__init__(Reminder, db)

    async def get_due_reminders_locked(
        self,
        now: datetime,
        limit: int = 100
    ) -> Sequence[Reminder]:
        """
        Get due reminders with row-level locking.
        
        Uses SELECT ... FOR UPDATE SKIP LOCKED to:
        - Lock selected rows to prevent other workers from processing them
        - Skip already locked rows (being processed by other workers)
        - Ensure each reminder is processed exactly once (idempotency)
        
        Args:
            now: Current UTC datetime
            limit: Maximum number of reminders to fetch
            
        Returns:
            List of locked Reminder objects with User relationship loaded
        """
        # Ensure now is timezone-aware UTC
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        
        query = (
            select(Reminder)
            .options(
                selectinload(Reminder.user),
                selectinload(Reminder.todo_list),
                selectinload(Reminder.note),
                selectinload(Reminder.medication),
                selectinload(Reminder.driver_document),
            )
            .where(
                and_(
                    Reminder.status == ReminderStatus.ACTIVE,
                    Reminder.remind_at_utc <= now,
                    Reminder.notified_at.is_(None),
                )
            )
            .order_by(Reminder.remind_at_utc.asc())
            .limit(limit)
            .with_for_update(
                skip_locked=True,
                nowait=False,
            )
        )
        
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_due_notifications_locked(
        self,
        now: datetime,
        limit: int = 100,
    ) -> Sequence[ReminderNotification]:
        """
        Get due notification deliveries with row-level locking.

        The worker idempotency unit is ReminderNotification, not Reminder:
        one reminder event can have several deliveries, for example one day
        before, one hour before, and at the exact event time.
        """
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        reminder_load = selectinload(ReminderNotification.reminder)
        query = (
            select(ReminderNotification)
            .join(Reminder, Reminder.id == ReminderNotification.reminder_id)
            .options(
                reminder_load.selectinload(Reminder.user),
                reminder_load.selectinload(Reminder.todo_list),
                reminder_load.selectinload(Reminder.note),
                reminder_load.selectinload(Reminder.medication),
                reminder_load.selectinload(Reminder.driver_document),
                reminder_load.selectinload(Reminder.notifications),
            )
            .where(
                and_(
                    ReminderNotification.status == ReminderNotificationStatus.PENDING,
                    ReminderNotification.notify_at_utc <= now,
                    Reminder.status == ReminderStatus.ACTIVE,
                )
            )
            .order_by(ReminderNotification.notify_at_utc.asc(), ReminderNotification.id.asc())
            .limit(limit)
            .with_for_update(
                skip_locked=True,
                nowait=False,
            )
        )

        result = await self.db.execute(query)
        return result.scalars().all()

    async def mark_as_notified(
        self,
        reminder_id: int,
        notified_at: datetime
    ) -> Optional[Reminder]:
        """
        Mark reminder as notified (idempotent operation).
        
        Sets notified_at timestamp to prevent duplicate notifications.
        This is the key to idempotency - even if worker crashes after
        sending but before marking, the next run will see notified_at
        is still None and can retry.
        
        Args:
            reminder_id: Reminder ID
            notified_at: UTC timestamp when notification was sent
            
        Returns:
            Updated Reminder or None if not found
        """
        if notified_at.tzinfo is None:
            notified_at = notified_at.replace(tzinfo=timezone.utc)
        
        query = (
            update(Reminder)
            .where(Reminder.id == reminder_id)
            .values(
                notified_at=notified_at,
                status=ReminderStatus.DONE,
            )
            .returning(Reminder)
        )
        
        result = await self.db.execute(query)
        await self.db.flush()
        return result.scalar_one_or_none()

    async def mark_notification_sent(
        self,
        notification_id: int,
        sent_at: datetime,
    ) -> Optional[ReminderNotification]:
        """Mark a single notification delivery as sent."""
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)

        query = (
            update(ReminderNotification)
            .where(ReminderNotification.id == notification_id)
            .values(
                status=ReminderNotificationStatus.SENT,
                sent_at_utc=sent_at,
                last_error=None,
            )
            .returning(ReminderNotification)
        )

        result = await self.db.execute(query)
        await self.db.flush()
        return result.scalar_one_or_none()

    async def mark_notification_canceled(
        self,
        notification_id: int,
        canceled_at: datetime,
        reason: Optional[str] = None,
    ) -> Optional[ReminderNotification]:
        """Mark a single pending notification as canceled."""
        if canceled_at.tzinfo is None:
            canceled_at = canceled_at.replace(tzinfo=timezone.utc)

        query = (
            update(ReminderNotification)
            .where(ReminderNotification.id == notification_id)
            .values(
                status=ReminderNotificationStatus.CANCELED,
                last_error=reason,
            )
            .returning(ReminderNotification)
        )

        result = await self.db.execute(query)
        await self.db.flush()
        return result.scalar_one_or_none()

    async def mark_notification_failed(
        self,
        notification_id: int,
        error: str,
    ) -> Optional[ReminderNotification]:
        """Close a notification after a permanent delivery failure."""
        query = (
            update(ReminderNotification)
            .where(ReminderNotification.id == notification_id)
            .values(
                status=ReminderNotificationStatus.FAILED,
                last_error=error[:1000],
            )
            .returning(ReminderNotification)
        )

        result = await self.db.execute(query)
        await self.db.flush()
        return result.scalar_one_or_none()

    async def remember_notification_error(
        self,
        notification_id: int,
        error: str,
    ) -> Optional[ReminderNotification]:
        """Save a retryable error while keeping the notification pending."""
        query = (
            update(ReminderNotification)
            .where(ReminderNotification.id == notification_id)
            .values(last_error=error[:1000])
            .returning(ReminderNotification)
        )

        result = await self.db.execute(query)
        await self.db.flush()
        return result.scalar_one_or_none()

    async def cancel_pending_notifications(
        self,
        reminder_id: int,
        reason: Optional[str] = None,
    ) -> None:
        """Cancel all future deliveries for a reminder."""
        query = (
            update(ReminderNotification)
            .where(
                and_(
                    ReminderNotification.reminder_id == reminder_id,
                    ReminderNotification.status == ReminderNotificationStatus.PENDING,
                )
            )
            .values(
                status=ReminderNotificationStatus.CANCELED,
                last_error=reason,
            )
        )
        await self.db.execute(query)
        await self.db.flush()

    async def mark_status(
        self,
        reminder_id: int,
        status: ReminderStatus
    ) -> Optional[Reminder]:
        """
        Update reminder status.
        
        Args:
            reminder_id: Reminder ID
            status: New status
            
        Returns:
            Updated Reminder or None
        """
        query = (
            update(Reminder)
            .where(Reminder.id == reminder_id)
            .values(status=status)
            .returning(Reminder)
        )
        
        result = await self.db.execute(query)
        await self.db.flush()
        return result.scalar_one_or_none()

    async def create_next_occurrence(
        self,
        reminder: Reminder,
        next_time: datetime,
        notify_offsets_minutes: Optional[Sequence[int]] = None,
    ) -> Reminder:
        """
        Create next occurrence of a recurring reminder.
        
        The original reminder is marked as notified, and a new reminder
        is created for the next occurrence with a new ID.
        
        Args:
            reminder: Original reminder
            next_time: UTC datetime for next occurrence
            
        Returns:
            New Reminder instance (not yet committed)
        """
        if next_time.tzinfo is None:
            next_time = next_time.replace(tzinfo=timezone.utc)
        
        new_reminder = Reminder(
            user_id=reminder.user_id,
            title=reminder.title,
            text=reminder.text,
            list_id=reminder.list_id,
            note_id=reminder.note_id,
            medication_id=reminder.medication_id,
            driver_document_id=reminder.driver_document_id,
            source_module=reminder.source_module,
            remind_at_utc=next_time,
            repeat_rule=reminder.repeat_rule,
            status=ReminderStatus.ACTIVE,
        )
        
        self.db.add(new_reminder)
        await self.db.flush()

        offsets = _normalize_notification_offsets(
            notify_offsets_minutes
            if notify_offsets_minutes is not None
            else _notification_offsets_from_reminder(reminder)
        )
        for offset in offsets:
            self.db.add(
                ReminderNotification(
                    reminder_id=new_reminder.id,
                    notify_at_utc=next_time - timedelta(minutes=offset),
                    offset_minutes=offset,
                    status=ReminderNotificationStatus.PENDING,
                )
            )
        await self.db.flush()
        return new_reminder

    async def get_active_by_user(
        self,
        user_id: int,
        limit: int = 50
    ) -> Sequence[Reminder]:
        """Get active reminders for a user."""
        query = (
            select(Reminder)
            .where(
                and_(
                    Reminder.user_id == user_id,
                    Reminder.status == ReminderStatus.ACTIVE,
                )
            )
            .order_by(Reminder.remind_at_utc.asc())
            .limit(limit)
        )
        
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_by_id_with_user(
        self,
        reminder_id: int
    ) -> Optional[Reminder]:
        """Get reminder with user relationship loaded."""
        query = (
            select(Reminder)
            .options(
                selectinload(Reminder.user),
                selectinload(Reminder.todo_list),
                selectinload(Reminder.note),
                selectinload(Reminder.medication),
                selectinload(Reminder.driver_document),
            )
            .where(Reminder.id == reminder_id)
        )
        
        result = await self.db.execute(query)
        return result.scalar_one_or_none()


def calculate_next_occurrence(
    remind_at: datetime,
    repeat_rule: RepeatRule,
    timezone_name: str = "UTC",
) -> datetime:
    """
    Calculate next occurrence time for a recurring reminder.
    
    Args:
        remind_at: Current reminder time (UTC)
        repeat_rule: Repeat rule
        timezone_name: User timezone for preserving local wall-clock time
        
    Returns:
        Next occurrence time (UTC)
    """
    if remind_at.tzinfo is None:
        remind_at = remind_at.replace(tzinfo=timezone.utc)

    try:
        user_tz = ZoneInfo(timezone_name or "UTC")
    except ZoneInfoNotFoundError:
        user_tz = ZoneInfo("UTC")

    local_time = remind_at.astimezone(user_tz)

    if repeat_rule == RepeatRule.DAILY:
        next_local = local_time + timedelta(days=1)
    elif repeat_rule == RepeatRule.WEEKLY:
        next_local = local_time + timedelta(weeks=1)
    elif repeat_rule == RepeatRule.MONTHLY:
        next_local = _add_one_month_preserving_wall_time(local_time)
    else:
        raise ValueError(f"Invalid repeat rule: {repeat_rule}")

    return next_local.astimezone(timezone.utc)


def _add_one_month_preserving_wall_time(value: datetime) -> datetime:
    """Add one calendar month and keep local time as stable as possible."""
    year = value.year + (value.month // 12)
    month = (value.month % 12) + 1
    current_last_day = calendar.monthrange(value.year, value.month)[1]
    target_last_day = calendar.monthrange(year, month)[1]

    if value.day == current_last_day:
        day = target_last_day
    else:
        day = min(value.day, target_last_day)

    return value.replace(year=year, month=month, day=day)


def _as_status_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _as_offset(value: int) -> int:
    offset = int(value)
    if offset < 0:
        raise ValueError("Notification offset must be non-negative")
    return offset


def _notification_status_is_active(status) -> bool:
    return _as_status_value(status) in {
        ReminderNotificationStatus.PENDING.value,
        ReminderNotificationStatus.SENT.value,
    }


def _dedupe_offsets(offsets: Sequence[int]) -> list[int]:
    values = {_as_offset(item) for item in offsets}
    values.add(0)
    return sorted(values, reverse=True)


def _loaded_notifications(reminder: Reminder) -> list[ReminderNotification]:
    notifications = getattr(reminder, "notifications", None)
    return list(notifications or [])


def _notification_offsets_from_reminder(reminder: Reminder) -> list[int]:
    notifications = _loaded_notifications(reminder)
    offsets = [
        item.offset_minutes
        for item in notifications
        if _notification_status_is_active(item.status)
    ]
    return _dedupe_offsets(offsets or [0])


def _normalize_notification_offsets(offsets: Optional[Sequence[int]]) -> list[int]:
    return _dedupe_offsets(offsets or [0])
