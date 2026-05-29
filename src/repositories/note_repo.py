"""Repository for user notes."""

from typing import Optional, Sequence

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Note
from src.repositories.base import BaseRepository


class NoteRepository(BaseRepository[Note]):
    """Repository for Note model with user ownership filters."""

    def __init__(self, db: AsyncSession):
        super().__init__(Note, db)

    async def get_for_user(
        self,
        note_id: int,
        user_id: int,
        *,
        include_archived: bool = False,
    ) -> Optional[Note]:
        """Return one note only if it belongs to the user."""
        query = select(Note).where(Note.id == note_id, Note.user_id == user_id)
        if not include_archived:
            query = query.where(Note.is_archived.is_not(True))
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_user(
        self,
        user_id: int,
        *,
        include_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Note]:
        """Return user's notes ordered by recent updates."""
        query = (
            select(Note)
            .where(Note.user_id == user_id)
            .order_by(Note.updated_at.desc(), Note.id.desc())
            .offset(offset)
            .limit(limit)
        )
        if not include_archived:
            query = query.where(Note.is_archived.is_not(True))
        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_by_user(self, user_id: int, *, include_archived: bool = False) -> int:
        """Count user's notes."""
        query = select(func.count(Note.id)).where(Note.user_id == user_id)
        if not include_archived:
            query = query.where(Note.is_archived.is_not(True))
        result = await self.db.execute(query)
        return result.scalar() or 0
