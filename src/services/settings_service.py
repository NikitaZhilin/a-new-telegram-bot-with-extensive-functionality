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
        
        Returns dict with counts of notes, lists, reminders.
        """
        from sqlalchemy import func
        from src.db.models import Note, TodoList, Reminder, ReminderStatus
        
        # Notes count
        notes_query = select(func.count(Note.id)).where(Note.user_id == user_id)
        notes_result = await self.db.execute(notes_query)
        notes_count = notes_result.scalar() or 0
        
        # Lists count
        lists_query = select(func.count(TodoList.id)).where(TodoList.user_id == user_id)
        lists_result = await self.db.execute(lists_query)
        lists_count = lists_result.scalar() or 0
        
        # Reminders count by status
        active_query = select(func.count(Reminder.id)).where(
            Reminder.user_id == user_id,
            Reminder.status == ReminderStatus.ACTIVE,
        )
        active_result = await self.db.execute(active_query)
        active_count = active_result.scalar() or 0
        
        done_query = select(func.count(Reminder.id)).where(
            Reminder.user_id == user_id,
            Reminder.status == ReminderStatus.DONE,
        )
        done_result = await self.db.execute(done_query)
        done_count = done_result.scalar() or 0
        
        return {
            "notes": notes_count,
            "lists": lists_count,
            "reminders": {
                "active": active_count,
                "done": done_count,
            },
        }
