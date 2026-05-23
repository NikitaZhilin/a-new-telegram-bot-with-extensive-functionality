"""
Note service for business logic.

Handles note CRUD operations with user timezone support.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from src.db.models import Note
from src.repositories.note_repo import NoteRepository

logger = logging.getLogger(__name__)


class NoteService:
    """Service for note operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = NoteRepository(db)

    async def create_note(
        self,
        user_id: int,
        title: str,
        text: Optional[str] = None,
    ) -> Note:
        """
        Create a new note.
        
        Args:
            user_id: User ID
            title: Note title
            text: Note body (optional)
            
        Returns:
            Created Note
        """
        note = Note(
            user_id=user_id,
            title=title,
            text=text,
        )
        self.db.add(note)
        await self.db.flush()
        await self.db.refresh(note)
        
        logger.info(f"Created note {note.id} for user {user_id}")
        return note

    async def get_note(self, note_id: int, user_id: int) -> Optional[Note]:
        """
        Get note by ID (must belong to user).
        
        Args:
            note_id: Note ID
            user_id: User ID (for ownership check)
            
        Returns:
            Note or None
        """
        query = select(Note).where(
            and_(Note.id == note_id, Note.user_id == user_id)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_notes_list(
        self,
        user_id: int,
        archived: bool = False,
        page: int = 0,
        page_size: int = 10,
    ) -> Tuple[List[Note], int]:
        """
        Get paginated list of notes.
        
        Args:
            user_id: User ID
            archived: Filter archived notes
            page: Page number (0-indexed)
            page_size: Items per page
            
        Returns:
            Tuple of (notes list, total count)
        """
        offset = page * page_size
        
        # Get notes
        notes = await self.repo.get_by_user(
            user_id=user_id,
            archived=archived,
            limit=page_size,
            offset=offset,
        )
        
        # Get total count
        count = await self.repo.count_by_user(
            user_id=user_id,
            archived=archived,
        )
        
        return list(notes), count

    async def update_note(
        self,
        note_id: int,
        user_id: int,
        title: Optional[str] = None,
        text: Optional[str] = None,
    ) -> Optional[Note]:
        """
        Update note fields.
        
        Args:
            note_id: Note ID
            user_id: User ID (for ownership check)
            title: New title (optional)
            text: New text (optional)
            
        Returns:
            Updated Note or None
        """
        note = await self.get_note(note_id, user_id)
        if not note:
            return None
        
        if title is not None:
            note.title = title
        if text is not None:
            note.text = text
        
        await self.db.flush()
        await self.db.refresh(note)
        
        logger.info(f"Updated note {note_id}")
        return note

    async def archive_note(self, note_id: int, user_id: int) -> Optional[Note]:
        """Archive a note."""
        note = await self.get_note(note_id, user_id)
        if not note:
            return None
        
        note.is_archived = True
        await self.db.flush()
        await self.db.refresh(note)
        
        logger.info(f"Archived note {note_id}")
        return note

    async def restore_note(self, note_id: int, user_id: int) -> Optional[Note]:
        """Restore an archived note."""
        note = await self.get_note(note_id, user_id)
        if not note:
            return None
        
        note.is_archived = False
        await self.db.flush()
        await self.db.refresh(note)
        
        logger.info(f"Restored note {note_id}")
        return note

    async def delete_note(self, note_id: int, user_id: int) -> bool:
        """
        Delete a note.
        
        Args:
            note_id: Note ID
            user_id: User ID (for ownership check)
            
        Returns:
            True if deleted, False if not found
        """
        note = await self.get_note(note_id, user_id)
        if not note:
            return False
        
        await self.db.delete(note)
        await self.db.flush()
        
        logger.info(f"Deleted note {note_id}")
        return True
