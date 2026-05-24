"""
Reminder service for business logic.

Handles reminder creation with timezone conversion.
All times are stored in UTC.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple

import pytz
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from src.db.models import Reminder, ReminderStatus, RepeatRule, User
from src.repositories.list_repo import ListRepository
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
        medication_id: Optional[int] = None,
        source_module: Optional[str] = None,
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
            medication_id: Optional linked Medication ID owned by the same user
            source_module: Domain that owns the reminder in user-facing lists
            
        Returns:
            Created Reminder
        """
        if list_id is not None:
            list_repo = ListRepository(self.db)
            list_obj = await list_repo.get_with_items(list_id, user_id)
            if not list_obj:
                logger.warning(
                    "Tried to create reminder for a list owned by another user or missing",
                    extra={"user_id": user_id, "list_id": list_id},
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

        # Ensure UTC timezone
        if remind_at_utc.tzinfo is None:
            remind_at_utc = remind_at_utc.replace(tzinfo=timezone.utc)

        if source_module is None:
            if medication_id is not None:
                source_module = "medication"
            elif list_id is not None:
                source_module = "list"
            else:
                source_module = "general"
        
        reminder = Reminder(
            user_id=user_id,
            title=title,
            text=text,
            list_id=list_id,
            medication_id=medication_id,
            source_module=source_module,
            remind_at_utc=remind_at_utc,
            repeat_rule=repeat_rule,
            status=ReminderStatus.ACTIVE,
        )
        self.db.add(reminder)
        await self.db.flush()
        await self.db.refresh(reminder)
        
        logger.info(f"Created reminder {reminder.id} for user {user_id} at {remind_at_utc}")
        return reminder

    async def get_reminder(self, reminder_id: int, user_id: int) -> Optional[Reminder]:
        """Get reminder by ID (must belong to user)."""
        query = select(Reminder).where(
            and_(Reminder.id == reminder_id, Reminder.user_id == user_id)
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
    ) -> Optional[Reminder]:
        """Update reminder time."""
        reminder = await self.get_reminder(reminder_id, user_id)
        if not reminder:
            return None
        
        if new_time_utc.tzinfo is None:
            new_time_utc = new_time_utc.replace(tzinfo=timezone.utc)
        
        reminder.remind_at_utc = new_time_utc
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
