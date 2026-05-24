"""List repository."""

import logging
from typing import Sequence, Optional
from sqlalchemy import select, and_, delete, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models import ListMember, TodoList, ListItem
from src.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class ListRepository(BaseRepository[TodoList]):
    """Repository for TodoList model."""

    def __init__(self, db: AsyncSession):
        super().__init__(TodoList, db)

    async def get_by_user(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
        source_module: Optional[str] = None,
    ) -> Sequence[TodoList]:
        """Get TodoLists for a user."""
        query = (
            select(TodoList)
            .where(TodoList.user_id == user_id)
            .order_by(TodoList.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        if source_module is not None:
            query = query.where(TodoList.source_module == source_module)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_accessible_by_user(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
        source_module: Optional[str] = "general",
    ) -> Sequence[TodoList]:
        """Get owned and shared TodoLists for a user."""
        query = (
            select(TodoList)
            .outerjoin(
                ListMember,
                and_(
                    ListMember.list_id == TodoList.id,
                    ListMember.user_id == user_id,
                ),
            )
            .options(selectinload(TodoList.items))
            .where(or_(TodoList.user_id == user_id, ListMember.user_id == user_id))
            .order_by(TodoList.updated_at.desc(), TodoList.id.desc())
            .offset(offset)
            .limit(limit)
        )
        if source_module is not None:
            query = query.where(TodoList.source_module == source_module)
        result = await self.db.execute(query)
        return result.scalars().unique().all()

    async def count_by_user(self, user_id: int, source_module: Optional[str] = None) -> int:
        """Count TodoLists for a user."""
        query = select(func.count(TodoList.id)).where(TodoList.user_id == user_id)
        if source_module is not None:
            query = query.where(TodoList.source_module == source_module)
        result = await self.db.execute(query)
        return result.scalar() or 0

    async def count_accessible_by_user(
        self,
        user_id: int,
        source_module: Optional[str] = "general",
    ) -> int:
        """Count owned and shared TodoLists for a user."""
        query = (
            select(func.count(func.distinct(TodoList.id)))
            .outerjoin(
                ListMember,
                and_(
                    ListMember.list_id == TodoList.id,
                    ListMember.user_id == user_id,
                ),
            )
            .where(or_(TodoList.user_id == user_id, ListMember.user_id == user_id))
        )
        if source_module is not None:
            query = query.where(TodoList.source_module == source_module)
        result = await self.db.execute(query)
        return result.scalar() or 0

    async def get_with_items(
        self,
        list_id: int,
        user_id: Optional[int] = None,
    ) -> Optional[TodoList]:
        """Get TodoList with items, optionally scoped to the owner."""
        query = (
            select(TodoList)
            .options(selectinload(TodoList.items))
            .where(TodoList.id == list_id)
        )
        if user_id is not None:
            query = query.where(TodoList.user_id == user_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_item_for_user(
        self,
        item_id: int,
        user_id: int,
    ) -> Optional[ListItem]:
        """Get a list item only if it belongs to the user."""
        query = (
            select(ListItem)
            .join(TodoList, TodoList.id == ListItem.list_id)
            .where(
                and_(
                    ListItem.id == item_id,
                    TodoList.user_id == user_id,
                )
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_items_for_user(
        self,
        list_id: int,
        user_id: int,
    ) -> Sequence[ListItem]:
        """Get list items only when the list belongs to the user."""
        query = (
            select(ListItem)
            .join(TodoList, TodoList.id == ListItem.list_id)
            .where(
                and_(
                    ListItem.list_id == list_id,
                    TodoList.user_id == user_id,
                )
            )
            .order_by(
                func.coalesce(ListItem.position, ListItem.id).asc(),
                ListItem.id.asc(),
            )
        )
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_item_in_list_for_user(
        self,
        item_id: int,
        list_id: int,
        user_id: int,
    ) -> Optional[ListItem]:
        """Get a list item scoped by list and owner."""
        query = (
            select(ListItem)
            .join(TodoList, TodoList.id == ListItem.list_id)
            .where(
                and_(
                    ListItem.id == item_id,
                    ListItem.list_id == list_id,
                    TodoList.user_id == user_id,
                )
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def add_item(
        self,
        list_id: int,
        text: str,
        position: Optional[int] = None,
    ) -> ListItem:
        """Add item to TodoList."""
        item = ListItem(
            list_id=list_id,
            text=text,
            is_completed=False,
            position=position,
        )
        self.db.add(item)
        await self.db.flush()
        await self.db.refresh(item)
        return item

    async def toggle_item(
        self,
        item_id: int,
    ) -> Optional[ListItem]:
        """Toggle item completion status."""
        query = select(ListItem).where(ListItem.id == item_id)
        result = await self.db.execute(query)
        item = result.scalar_one_or_none()

        if item:
            item.is_completed = item.is_completed is not True
            await self.db.flush()
            await self.db.refresh(item)

        return item

    async def toggle_item_for_user(
        self,
        item_id: int,
        user_id: int,
    ) -> Optional[ListItem]:
        """Toggle item completion only if the item belongs to the user."""
        item = await self.get_item_for_user(item_id, user_id)

        if item:
            item.is_completed = item.is_completed is not True
            await self.db.flush()
            await self.db.refresh(item)

        return item

    async def update_item_text_for_user(
        self,
        item_id: int,
        user_id: int,
        new_text: str,
    ) -> Optional[ListItem]:
        """Update item text only if the item belongs to the user."""
        item = await self.get_item_for_user(item_id, user_id)

        if item:
            item.text = new_text
            await self.db.flush()
            await self.db.refresh(item)

        return item

    async def delete_item(self, item_id: int) -> None:
        """Delete item from TodoList."""
        await self.db.execute(
            delete(ListItem).where(ListItem.id == item_id)
        )
        await self.db.flush()

    async def delete_item_for_user(
        self,
        item_id: int,
        user_id: int,
    ) -> bool:
        """Delete item only if the item belongs to the user."""
        item = await self.get_item_for_user(item_id, user_id)
        if not item:
            return False

        await self.db.delete(item)
        await self.db.flush()
        return True
