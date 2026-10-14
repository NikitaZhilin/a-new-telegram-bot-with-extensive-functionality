"""User feedback: bug reports and ideas sent to the developer from the bot."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import ErrorEvent, UserFeedback

KIND_LABELS = {
    "bug": "🐞 Ошибка",
    "idea": "💡 Идея или доработка",
    "other": "✉️ Другое",
}
STATUS_LABELS = {"new": "новое", "read": "прочитано", "answered": "отвечено"}
MAX_TEXT = 3000
HOURLY_LIMIT = 10


class FeedbackLimitError(Exception):
    """Too many messages in a short time."""


class FeedbackService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        telegram_id: int,
        kind: str,
        text: str,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        photo_file_id: Optional[str] = None,
        app_version: Optional[str] = None,
    ) -> UserFeedback:
        since = datetime.now(timezone.utc) - timedelta(hours=1)
        recent = await self.session.scalar(
            select(func.count())
            .select_from(UserFeedback)
            .where(UserFeedback.telegram_id == telegram_id, UserFeedback.created_at >= since)
        )
        if (recent or 0) >= HOURLY_LIMIT:
            raise FeedbackLimitError
        item = UserFeedback(
            user_id=user_id,
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            kind=kind if kind in KIND_LABELS else "other",
            text=(text or "").strip()[:MAX_TEXT],
            photo_file_id=photo_file_id,
            app_version=app_version,
            status="new",
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(item)
        await self.session.flush()
        return item

    async def get(self, feedback_id: int) -> Optional[UserFeedback]:
        return await self.session.get(UserFeedback, feedback_id)

    async def list(self, *, status: Optional[str] = None, limit: int = 100) -> list[UserFeedback]:
        query = select(UserFeedback)
        if status:
            query = query.where(UserFeedback.status == status)
        query = query.order_by(UserFeedback.created_at.desc(), UserFeedback.id.desc()).limit(limit)
        return list((await self.session.execute(query)).scalars().all())

    async def count_new(self) -> int:
        return int(
            await self.session.scalar(
                select(func.count()).select_from(UserFeedback).where(UserFeedback.status == "new")
            )
            or 0
        )

    async def set_status(self, feedback_id: int, status: str) -> Optional[UserFeedback]:
        if status not in STATUS_LABELS:
            raise ValueError(status)
        item = await self.get(feedback_id)
        if item is None:
            return None
        item.status = status
        await self.session.flush()
        return item

    async def save_reply(self, feedback_id: int, reply: str) -> Optional[UserFeedback]:
        item = await self.get(feedback_id)
        if item is None:
            return None
        item.admin_reply = reply.strip()[:MAX_TEXT]
        item.status = "answered"
        item.answered_at = datetime.now(timezone.utc)
        await self.session.flush()
        return item

    async def recent_errors_for(self, telegram_id: int, hours: int = 24, limit: int = 5) -> list[ErrorEvent]:
        """Errors this user hit lately: helps to match a bug report with the journal."""
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        result = await self.session.execute(
            select(ErrorEvent)
            .where(ErrorEvent.telegram_id == telegram_id, ErrorEvent.last_seen_at >= since)
            .order_by(ErrorEvent.last_seen_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
