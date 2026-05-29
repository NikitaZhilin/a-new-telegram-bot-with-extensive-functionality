"""Business logic for personal text notes."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Note
from src.repositories.note_repo import NoteRepository


MAX_NOTE_TITLE_LENGTH = 255
MAX_NOTE_TEXT_LENGTH = 20000
MAX_NOTE_SEARCH_LENGTH = 120
NOTE_CATEGORIES: dict[str, str] = {
    "recipe": "Рецепт",
    "instruction": "Инструкция",
    "idea": "Идея",
    "personal": "Личное",
    "other": "Другое",
}
DEFAULT_NOTE_CATEGORY = "other"


def _clean_title(title: str) -> str:
    value = (title or "").strip()
    if not value:
        raise ValueError("Название заметки не может быть пустым")
    if len(value) > MAX_NOTE_TITLE_LENGTH:
        raise ValueError(f"Название заметки не должно быть длиннее {MAX_NOTE_TITLE_LENGTH} символов")
    return value


def _clean_text(text: Optional[str]) -> str:
    value = (text or "").strip()
    if len(value) > MAX_NOTE_TEXT_LENGTH:
        raise ValueError(f"Текст заметки не должен быть длиннее {MAX_NOTE_TEXT_LENGTH} символов")
    return value


def _clean_search_query(search_query: Optional[str]) -> str | None:
    value = (search_query or "").strip()
    if not value:
        return None
    if len(value) > MAX_NOTE_SEARCH_LENGTH:
        raise ValueError(f"Поисковый запрос не должен быть длиннее {MAX_NOTE_SEARCH_LENGTH} символов")
    return value


def clean_note_category(category: Optional[str]) -> str:
    """Normalize note category to a known allowlisted value."""
    value = (category or DEFAULT_NOTE_CATEGORY).strip().lower()
    if value not in NOTE_CATEGORIES:
        raise ValueError("Неизвестная категория заметки")
    return value


def note_category_label(category: Optional[str]) -> str:
    """Return user-facing category label."""
    value = (category or DEFAULT_NOTE_CATEGORY).strip().lower()
    return NOTE_CATEGORIES.get(value, NOTE_CATEGORIES[DEFAULT_NOTE_CATEGORY])


class NoteService:
    """Service for user-owned standalone notes."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = NoteRepository(db)

    async def create_note(
        self,
        user_id: int,
        title: str,
        text: Optional[str] = None,
        *,
        category: Optional[str] = None,
    ) -> Note:
        """Create a personal note."""
        note = Note(
            user_id=user_id,
            title=_clean_title(title),
            text=_clean_text(text),
            category=clean_note_category(category),
            is_archived=False,
        )
        self.db.add(note)
        await self.db.flush()
        await self.db.refresh(note)
        return note

    async def list_notes(
        self,
        user_id: int,
        *,
        page: int = 0,
        page_size: int = 10,
        include_archived: bool = False,
        search_query: Optional[str] = None,
        category: Optional[str] = None,
    ) -> tuple[list[Note], int]:
        """Return paginated user notes."""
        page = max(page, 0)
        page_size = max(1, min(page_size, 50))
        search_value = _clean_search_query(search_query)
        category_value = clean_note_category(category) if category else None
        notes = list(
            await self.repo.get_by_user(
                user_id,
                include_archived=include_archived,
                limit=page_size,
                offset=page * page_size,
                search_query=search_value,
                category=category_value,
            )
        )
        total = await self.repo.count_by_user(
            user_id,
            include_archived=include_archived,
            search_query=search_value,
            category=category_value,
        )
        return notes, total

    async def get_note(self, note_id: int, user_id: int, *, include_archived: bool = False) -> Optional[Note]:
        """Return a user-owned note."""
        return await self.repo.get_for_user(note_id, user_id, include_archived=include_archived)

    async def update_note(
        self,
        note_id: int,
        user_id: int,
        *,
        title: Optional[str] = None,
        text: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Optional[Note]:
        """Update title, text, and/or category of a user-owned note."""
        note = await self.get_note(note_id, user_id)
        if not note:
            return None

        if title is not None:
            note.title = _clean_title(title)
        if text is not None:
            note.text = _clean_text(text)
        if category is not None:
            note.category = clean_note_category(category)
        note.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(note)
        return note

    async def archive_note(self, note_id: int, user_id: int) -> bool:
        """Archive a user-owned note so it disappears from active views."""
        note = await self.get_note(note_id, user_id)
        if not note:
            return False
        note.is_archived = True
        note.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return True
