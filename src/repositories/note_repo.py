"""Repository for user notes."""

from typing import Optional, Sequence

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Note
from src.repositories.base import BaseRepository


class NoteRepository(BaseRepository[Note]):
    """Repository for Note model with user ownership filters."""

    def __init__(self, db: AsyncSession):
        super().__init__(Note, db)

    @staticmethod
    def _search_pattern(search_query: str | None) -> str | None:
        """Build an escaped ILIKE pattern for user-entered note search."""
        value = (search_query or "").strip()
        if not value:
            return None
        escaped = (
            value.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        return f"%{escaped}%"

    @classmethod
    def _apply_search(cls, query, search_query: str | None):
        """Apply title/body search to a note query."""
        pattern = cls._search_pattern(search_query)
        if not pattern:
            return query
        return query.where(
            or_(
                Note.title.ilike(pattern, escape="\\"),
                Note.text.ilike(pattern, escape="\\"),
            )
        )

    @staticmethod
    def _apply_category(query, category: str | None):
        """Apply optional category filter."""
        if not category:
            return query
        return query.where(Note.category == category)

    @staticmethod
    def _apply_pinned(query, pinned_only: bool):
        """Apply optional pinned-only filter."""
        if not pinned_only:
            return query
        return query.where(Note.is_pinned.is_(True))

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
        search_query: str | None = None,
        category: str | None = None,
        pinned_only: bool = False,
    ) -> Sequence[Note]:
        """Return user's notes ordered by recent updates."""
        query = (
            select(Note)
            .where(Note.user_id == user_id)
            .order_by(Note.is_pinned.desc(), Note.updated_at.desc(), Note.id.desc())
            .offset(offset)
            .limit(limit)
        )
        if not include_archived:
            query = query.where(Note.is_archived.is_not(True))
        query = self._apply_search(query, search_query)
        query = self._apply_category(query, category)
        query = self._apply_pinned(query, pinned_only)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_by_user(
        self,
        user_id: int,
        *,
        include_archived: bool = False,
        search_query: str | None = None,
        category: str | None = None,
        pinned_only: bool = False,
    ) -> int:
        """Count user's notes."""
        query = select(func.count(Note.id)).where(Note.user_id == user_id)
        if not include_archived:
            query = query.where(Note.is_archived.is_not(True))
        query = self._apply_search(query, search_query)
        query = self._apply_category(query, category)
        query = self._apply_pinned(query, pinned_only)
        result = await self.db.execute(query)
        return result.scalar() or 0
