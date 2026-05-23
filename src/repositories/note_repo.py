"""Note repository."""

import logging
from typing import Sequence, Optional
from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Note
from src.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class NoteRepository(BaseRepository[Note]):
    """Repository for Note model."""

    def __init__(self, db: AsyncSession):
        super().__init__(Note, db)

    async def get_by_user(
        self,
        user_id: int,
        archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Note]:
        """Get notes for a user."""
        query = (
            select(Note)
            .where(
                and_(
                    Note.user_id == user_id,
                    Note.is_archived == archived,
                )
            )
            .order_by(Note.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_by_user(
        self,
        user_id: int,
        archived: bool = False,
    ) -> int:
        """Count notes for a user."""
        from sqlalchemy import func
        
        query = (
            select(func.count(Note.id))
            .where(
                and_(
                    Note.user_id == user_id,
                    Note.is_archived == archived,
                )
            )
        )
        result = await self.db.execute(query)
        return result.scalar() or 0

    async def archive(self, note_id: int) -> Optional[Note]:
        """Archive a note."""
        query = (
            update(Note)
            .where(Note.id == note_id)
            .values(is_archived=True)
            .returning(Note)
        )
        result = await self.db.execute(query)
        await self.db.flush()
        return result.scalar_one_or_none()

    async def restore(self, note_id: int) -> Optional[Note]:
        """Restore an archived note."""
        query = (
            update(Note)
            .where(Note.id == note_id)
            .values(is_archived=False)
            .returning(Note)
        )
        result = await self.db.execute(query)
        await self.db.flush()
        return result.scalar_one_or_none()
