"""User repository."""

import logging
from typing import Optional, Sequence
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import User, UserSubscription
from src.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class UserRepository(BaseRepository[User]):
    """Repository for User model."""

    def __init__(self, db: AsyncSession):
        super().__init__(User, db)

    async def get_by_telegram_id(
        self,
        telegram_id: int
    ) -> Optional[User]:
        """Get user by Telegram ID."""
        query = select(User).where(User.telegram_id == telegram_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_all_with_telegram_id(self, limit: int = 1000) -> Sequence[User]:
        """Get users that can receive Telegram messages."""
        query = (
            select(User)
            .where(User.telegram_id.is_not(None))
            .order_by(User.id.asc())
            .limit(limit)
        )
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_or_create(
        self,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> User:
        """Get existing user or create new one."""
        user = await self.get_by_telegram_id(telegram_id)
        
        if user:
            user.is_admin = telegram_id in settings.admin_telegram_id_set
            if user.timezone == "UTC" and settings.TIMEZONE_DEFAULT != "UTC":
                user.timezone = settings.TIMEZONE_DEFAULT
            # Update info if changed
            if username and username != user.username:
                user.username = username
            if first_name and first_name != user.first_name:
                user.first_name = first_name
            if last_name and last_name != user.last_name:
                user.last_name = last_name
            await self.db.flush()
            return user
        
        # Create new user
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            timezone=settings.TIMEZONE_DEFAULT,
            is_admin=telegram_id in settings.admin_telegram_id_set,
            onboarding_source="telegram_link",
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        subscription = UserSubscription(
            user_id=user.id,
            plan_code=settings.DEFAULT_SUBSCRIPTION_PLAN,
            status="active",
        )
        self.db.add(subscription)
        await self.db.flush()
        user.subscriptions.append(subscription)
        return user

    async def set_timezone(
        self,
        user_id: int,
        timezone: str
    ) -> Optional[User]:
        """Set user's timezone."""
        user = await self.get(user_id)
        if user:
            user.timezone = timezone
            await self.db.flush()
            await self.db.refresh(user)
        return user
