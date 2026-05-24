"""
Settings service for user preferences.
"""

import logging
from typing import Optional

import pytz
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.db.models import User
from src.repositories.user_repo import UserRepository
from src.services.driver_service import DriverService

logger = logging.getLogger(__name__)


class SettingsService:
    """Service for user settings."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = UserRepository(db)

    async def get_user(self, user_id: int) -> Optional[User]:
        """Get user by ID."""
        return await self.repo.get(user_id)

    async def set_timezone(self, user_id: int, timezone_str: str) -> Optional[User]:
        """
        Set user's timezone.
        
        Args:
            user_id: User ID
            timezone_str: Timezone string (e.g., 'Europe/Moscow')
            
        Returns:
            Updated User or None
            
        Raises:
            ValueError: If timezone is invalid
        """
        # Validate timezone
        try:
            pytz.timezone(timezone_str)
        except pytz.exceptions.UnknownTimeZoneError:
            raise ValueError(f"Invalid timezone: {timezone_str}")
        
        user = await self.repo.get(user_id)
        if not user:
            return None
        
        user.timezone = timezone_str
        await self.db.flush()
        await self.db.refresh(user)
        
        logger.info(f"Set timezone {timezone_str} for user {user_id}")
        return user

    async def get_stats(self, user_id: int) -> dict:
        """
        Get user statistics.
        
        Returns dict with counts of notes, lists, reminders, medications.
        """
        from sqlalchemy import func
        from src.db.models import (
            ListMember,
            Medication,
            Note,
            Reminder,
            ReminderStatus,
            TodoList,
        )

        async def count(query) -> int:
            result = await self.db.execute(query)
            return result.scalar() or 0

        notes_active = await count(
            select(func.count(Note.id)).where(Note.user_id == user_id, Note.is_archived.is_(False))
        )
        notes_archived = await count(
            select(func.count(Note.id)).where(Note.user_id == user_id, Note.is_archived.is_(True))
        )

        owned_lists = await count(select(func.count(TodoList.id)).where(TodoList.user_id == user_id))
        shared_lists = await count(select(func.count(ListMember.id)).where(ListMember.user_id == user_id))

        reminders_active = await count(
            select(func.count(Reminder.id)).where(
                Reminder.user_id == user_id,
                Reminder.status == ReminderStatus.ACTIVE,
            )
        )
        reminders_done = await count(
            select(func.count(Reminder.id)).where(
                Reminder.user_id == user_id,
                Reminder.status == ReminderStatus.DONE,
            )
        )
        reminders_canceled = await count(
            select(func.count(Reminder.id)).where(
                Reminder.user_id == user_id,
                Reminder.status == ReminderStatus.CANCELED,
            )
        )
        reminders_missed = await count(
            select(func.count(Reminder.id)).where(
                Reminder.user_id == user_id,
                Reminder.status == ReminderStatus.MISSED,
            )
        )

        medications_active = await count(
            select(func.count(Medication.id)).where(
                Medication.user_id == user_id,
                Medication.is_active.is_(True),
            )
        )
        medications_archived = await count(
            select(func.count(Medication.id)).where(
                Medication.user_id == user_id,
                Medication.is_active.is_(False),
            )
        )
        driver_overview = await DriverService(self.db).get_user_overview(user_id)
        
        return {
            "notes": {
                "active": notes_active,
                "archived": notes_archived,
            },
            "lists": {
                "owned": owned_lists,
                "shared": shared_lists,
            },
            "reminders": {
                "active": reminders_active,
                "done": reminders_done,
                "canceled": reminders_canceled,
                "missed": reminders_missed,
            },
            "medications": {
                "active": medications_active,
                "archived": medications_archived,
            },
            "driver": driver_overview,
        }
