"""
Reminder service for business logic.

Handles reminder creation with timezone conversion.
All times are stored in UTC.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Sequence, Tuple

import pytz
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from src.db.models import (
    DriverDocument,
    Reminder,
    ReminderNotification,
    ReminderNotificationStatus,
    ReminderStatus,
    RepeatRule,
    User,
)
from src.repositories.medication_repo import MedicationRepository
from src.repositories.reminder_repo import ReminderRepository

logger = logging.getLogger(__name__)


class ReminderService:
    """Service for reminder operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ReminderRepository(db)

    async def create_reminder(
        self,
        user_id: int,
        text: str,
        remind_at_utc: datetime,
        title: Optional[str] = None,
        repeat_rule: RepeatRule = RepeatRule.NONE,
        list_id: Optional[int] = None,
        note_id: Optional[int] = None,
        medication_id: Optional[int] = None,
        driver_document_id: Optional[int] = None,
        source_module: Optional[str] = None,
        notify_offsets_minutes: Optional[Sequence[int]] = None,
    ) -> Optional[Reminder]:
        """
        Create a new reminder.
        
        Args:
            user_id: User ID
            text: Reminder text
            remind_at_utc: Reminder time in UTC (timezone-aware)
            title: Optional title
            repeat_rule: Repeat rule
            list_id: Optional linked TodoList ID owned by the same user
            note_id: Optional linked Note ID owned by the same user
            medication_id: Optional linked Medication ID owned by the same user
            driver_document_id: Optional linked DriverDocument ID owned by the same user
            source_module: Domain that owns the reminder in user-facing lists
            notify_offsets_minutes: Notification offsets before the reminder event
            
        Returns:
            Created Reminder
        """
        linked_targets = sum(
            1
            for value in (list_id, note_id, medication_id, driver_document_id)
            if value is not None
        )
        if linked_targets > 1:
            logger.warning(
                "Tried to create reminder with multiple linked domain targets",
                extra={
                    "user_id": user_id,
                    "list_id": list_id,
                    "note_id": note_id,
                    "medication_id": medication_id,
                    "driver_document_id": driver_document_id,
                },
            )
            return None

        if list_id is not None:
            from src.services.list_service import ListService

            if not await ListService(self.db).can_view(list_id, user_id, source_module=None):
                logger.warning(
                    "Tried to create reminder for a list without access or missing",
                    extra={"user_id": user_id, "list_id": list_id},
                )
                return None

        if note_id is not None:
            from src.services.note_service import NoteService

            note = await NoteService(self.db).get_note(note_id, user_id)
            if not note:
                logger.warning(
                    "Tried to create reminder for a note owned by another user, archived, or missing",
                    extra={"user_id": user_id, "note_id": note_id},
                )
                return None

        if medication_id is not None:
            medication_repo = MedicationRepository(self.db)
            medication = await medication_repo.get_for_user(medication_id, user_id)
            if not medication:
                logger.warning(
                    "Tried to create reminder for a medication owned by another user or missing",
                    extra={"user_id": user_id, "medication_id": medication_id},
                )
                return None

        if driver_document_id is not None:
            result = await self.db.execute(
                select(DriverDocument).where(
                    DriverDocument.id == driver_document_id,
                    DriverDocument.user_id == user_id,
                )
            )
            if not result.scalar_one_or_none():
                logger.warning(
                    "Tried to create reminder for a driver document owned by another user or missing",
                    extra={"user_id": user_id, "driver_document_id": driver_document_id},
                )
                return None

        # Ensure UTC timezone
        remind_at_utc = self._ensure_utc(remind_at_utc)

        if source_module is None:
            if medication_id is not None:
                source_module = "medication"
            elif driver_document_id is not None:
                source_module = "driver"
            elif note_id is not None:
                source_module = "note"
            elif list_id is not None:
                source_module = "list"
            else:
                source_module = "general"
        
        reminder = Reminder(
            user_id=user_id,
            title=title,
            text=text,
            list_id=list_id,
            note_id=note_id,
            medication_id=medication_id,
            driver_document_id=driver_document_id,
            source_module=source_module,
            remind_at_utc=remind_at_utc,
            repeat_rule=repeat_rule,
            status=ReminderStatus.ACTIVE,
        )
        self.db.add(reminder)
        await self.db.flush()
        self._add_notification_plan(
            reminder,
            notify_offsets_minutes,
        )
        await self.db.flush()
        await self.db.refresh(reminder)
        
        logger.info(f"Created reminder {reminder.id} for user {user_id} at {remind_at_utc}")
        return reminder

    async def get_reminder(self, reminder_id: int, user_id: int) -> Optional[Reminder]:
        """Get reminder by ID (must belong to user)."""
        query = (
            select(Reminder)
            .options(
                selectinload(Reminder.todo_list),
                selectinload(Reminder.note),
                selectinload(Reminder.medication),
                selectinload(Reminder.driver_document),
                selectinload(Reminder.notifications),
            )
            .where(and_(Reminder.id == reminder_id, Reminder.user_id == user_id))
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_reminders_list(
        self,
        user_id: int,
        active: bool = True,
        page: int = 0,
        page_size: int = 20,
        source_module: Optional[str] = "general",
    ) -> Tuple[List[Reminder], int]:
        """Get paginated list of reminders."""
        from sqlalchemy import func
        
        offset = page * page_size
        status = ReminderStatus.ACTIVE if active else None
        
        # Get reminders
        conditions = [
            Reminder.user_id == user_id,
            Reminder.status == status if status else Reminder.status != ReminderStatus.ACTIVE,
        ]
        if source_module is not None:
            conditions.append(Reminder.source_module == source_module)

        query = (
            select(Reminder)
            .where(and_(*conditions))
            .order_by(Reminder.remind_at_utc.asc())
            .offset(offset)
            .limit(page_size)
        )
        
        result = await self.db.execute(query)
        reminders = result.scalars().all()
        
        # Get total count
        count_query = select(func.count(Reminder.id)).where(and_(*conditions))
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0
        
        return list(reminders), total

    async def update_reminder_time(
        self,
        reminder_id: int,
        user_id: int,
        new_time_utc: datetime,
        notify_offsets_minutes: Optional[Sequence[int]] = None,
    ) -> Optional[Reminder]:
        """Update reminder time."""
        reminder = await self.get_reminder(reminder_id, user_id)
        if not reminder:
            return None
        
        new_time_utc = self._ensure_utc(new_time_utc)
        offsets = (
            self._normalize_notification_offsets(notify_offsets_minutes)
            if notify_offsets_minutes is not None
            else self._active_notification_offsets(reminder)
        )
        
        reminder.remind_at_utc = new_time_utc
        self._cancel_pending_notifications(reminder)
        self._add_notification_plan(reminder, offsets)
        await self.db.flush()
        await self.db.refresh(reminder)
        
        logger.info(f"Updated reminder {reminder_id} time to {new_time_utc}")
        return reminder

    async def update_reminder_text(
        self,
        reminder_id: int,
        user_id: int,
        new_text: str,
    ) -> Optional[Reminder]:
        """Update reminder text."""
        reminder = await self.get_reminder(reminder_id, user_id)
        if not reminder:
            return None
        
        reminder.text = new_text
        await self.db.flush()
        await self.db.refresh(reminder)
        
        logger.info(f"Updated reminder {reminder_id} text")
        return reminder

    async def update_reminder_repeat(
        self,
        reminder_id: int,
        user_id: int,
        repeat_rule: RepeatRule,
    ) -> Optional[Reminder]:
        """Update reminder repeat rule."""
        reminder = await self.get_reminder(reminder_id, user_id)
        if not reminder:
            return None
        
        reminder.repeat_rule = repeat_rule
        await self.db.flush()
        await self.db.refresh(reminder)
        
        logger.info(f"Updated reminder {reminder_id} repeat rule to {repeat_rule}")
        return reminder

    async def update_notification_plan(
        self,
        reminder_id: int,
        user_id: int,
        notify_offsets_minutes: Sequence[int],
    ) -> Optional[Reminder]:
        """Replace pending notification deliveries without changing reminder time."""
        reminder = await self.get_reminder(reminder_id, user_id)
        if not reminder:
            return None

        offsets = self._normalize_notification_offsets(notify_offsets_minutes)
        self._cancel_pending_notifications(reminder)
        self._add_notification_plan(reminder, offsets)
        await self.db.flush()
        await self.db.refresh(reminder)

        logger.info(f"Updated reminder {reminder_id} notification plan")
        return reminder

    async def mark_reminder_done(
        self,
        reminder_id: int,
        user_id: int,
    ) -> Optional[Reminder]:
        """Mark reminder as done."""
        reminder = await self.get_reminder(reminder_id, user_id)
        if not reminder:
            return None
        
        reminder.status = ReminderStatus.DONE
        self._cancel_pending_notifications(reminder)
        await self.db.flush()
        await self.db.refresh(reminder)
        
        logger.info(f"Marked reminder {reminder_id} as done")
        return reminder

    async def mark_reminder_canceled(
        self,
        reminder_id: int,
        user_id: int,
    ) -> Optional[Reminder]:
        """Mark reminder as canceled."""
        reminder = await self.get_reminder(reminder_id, user_id)
        if not reminder:
            return None
        
        reminder.status = ReminderStatus.CANCELED
        self._cancel_pending_notifications(reminder)
        await self.db.flush()
        await self.db.refresh(reminder)
        
        logger.info(f"Marked reminder {reminder_id} as canceled")
        return reminder

    async def delete_reminder(self, reminder_id: int, user_id: int) -> bool:
        """Delete a reminder."""
        reminder = await self.get_reminder(reminder_id, user_id)
        if not reminder:
            return False
        
        await self.db.delete(reminder)
        await self.db.flush()
        
        logger.info(f"Deleted reminder {reminder_id}")
        return True

    async def can_complete_reminder(
        self,
        reminder_id: int,
        user_id: int,
        now_utc: Optional[datetime] = None,
        action_window: timedelta = timedelta(hours=2),
    ) -> bool:
        """Return whether user-facing UI should expose the done action."""
        reminder = await self.get_reminder(reminder_id, user_id)
        if not reminder or reminder.status != ReminderStatus.ACTIVE:
            return False

        now_utc = self._ensure_utc(now_utc or datetime.now(timezone.utc))
        remind_at = self._ensure_utc(reminder.remind_at_utc)
        if now_utc >= remind_at - action_window:
            return True

        return any(
            notification.status == ReminderNotificationStatus.SENT
            for notification in reminder.notifications
        )

    async def get_user(self, user_id: int) -> Optional[User]:
        """Get user for timezone lookup."""
        query = select(User).where(User.id == user_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    def convert_user_time_to_utc(
        self,
        dt: datetime,
        user_timezone: str,
    ) -> datetime:
        """
        Convert user's local time to UTC.
        
        Args:
            dt: Datetime in user's timezone (may be naive or aware)
            user_timezone: User's timezone string (e.g., 'Europe/Moscow')
            
        Returns:
            UTC datetime (timezone-aware)
        """
        tz = pytz.timezone(user_timezone)
        
        if dt.tzinfo is None:
            # Naive datetime - assume it's in user's timezone
            dt = tz.localize(dt)
        else:
            # Aware datetime - convert to user's timezone
            dt = dt.astimezone(tz)
        
        # Convert to UTC
        return dt.astimezone(timezone.utc)

    def convert_utc_to_user_time(
        self,
        dt_utc: datetime,
        user_timezone: str,
    ) -> datetime:
        """
        Convert UTC datetime to user's local time.
        
        Args:
            dt_utc: UTC datetime (timezone-aware)
            user_timezone: User's timezone string
            
        Returns:
            Datetime in user's timezone
        """
        tz = pytz.timezone(user_timezone)
        return dt_utc.astimezone(tz)

    @staticmethod
    def _ensure_utc(value: datetime) -> datetime:
        """Normalize datetime to timezone-aware UTC."""
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _normalize_notification_offsets(
        offsets: Optional[Sequence[int]],
    ) -> list[int]:
        """Return distinct non-negative notification offsets."""
        if not offsets:
            return [0]

        normalized: set[int] = {0}
        for value in offsets:
            offset = int(value)
            if offset < 0:
                raise ValueError("Notification offset must be non-negative")
            normalized.add(offset)
        return sorted(normalized, reverse=True) or [0]

    def _add_notification_plan(
        self,
        reminder: Reminder,
        offsets: Optional[Sequence[int]],
    ) -> None:
        """Attach notification rows to one reminder event."""
        remind_at = self._ensure_utc(reminder.remind_at_utc)
        for offset in self._normalize_notification_offsets(offsets):
            self.db.add(
                ReminderNotification(
                    reminder_id=reminder.id,
                    notify_at_utc=remind_at - timedelta(minutes=offset),
                    offset_minutes=offset,
                    status=ReminderNotificationStatus.PENDING,
                )
            )

    @staticmethod
    def _active_notification_offsets(reminder: Reminder) -> list[int]:
        """Preserve pending notification offsets when only the event time changes."""
        offsets = [
            item.offset_minutes
            for item in reminder.notifications
            if item.status == ReminderNotificationStatus.PENDING
        ]
        return sorted(set(offsets), reverse=True) or [0]

    @staticmethod
    def _cancel_pending_notifications(reminder: Reminder) -> None:
        """Cancel future notification rows while preserving sent history."""
        for notification in reminder.notifications:
            if notification.status == ReminderNotificationStatus.PENDING:
                notification.status = ReminderNotificationStatus.CANCELED
