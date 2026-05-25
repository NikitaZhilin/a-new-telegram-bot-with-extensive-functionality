"""
List service for business logic.

Handles TodoList and list item CRUD operations.
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models import ListMember, ListShareToken, TodoList, ListItem, User
from src.repositories.list_repo import ListRepository

logger = logging.getLogger(__name__)

LIST_ROLES = {"owner", "editor", "viewer"}
EDIT_ROLES = {"owner", "editor"}


class ListService:
    """Service for TodoList operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ListRepository(db)

    async def create_list(
        self,
        user_id: int,
        title: str,
        source_module: str = "general",
    ) -> TodoList:
        """Create a new TodoList."""
        list_obj = TodoList(
            user_id=user_id,
            title=title,
            source_module=source_module,
        )
        self.db.add(list_obj)
        await self.db.flush()
        await self.db.refresh(list_obj)

        logger.info(f"Created TodoList {list_obj.id} for user {user_id}")
        return list_obj

    async def get_list(
        self,
        list_id: int,
        user_id: int,
        source_module: Optional[str] = "general",
    ) -> Optional[TodoList]:
        """Get TodoList by ID with access check."""
        if not await self.can_view(list_id, user_id, source_module=source_module):
            return None
        list_obj = await self.repo.get_with_items(list_id)
        if list_obj and source_module is not None and list_obj.source_module != source_module:
            return None
        return list_obj

    async def get_access_role(
        self,
        list_id: int,
        user_id: int,
        source_module: Optional[str] = "general",
    ) -> Optional[str]:
        """Return user's role for a list."""
        list_obj = await self.repo.get_with_items(list_id)
        if not list_obj:
            return None
        if source_module is not None and list_obj.source_module != source_module:
            return None
        if list_obj.user_id == user_id:
            return "owner"

        result = await self.db.execute(
            select(ListMember.role).where(
                and_(
                    ListMember.list_id == list_id,
                    ListMember.user_id == user_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def can_view(
        self,
        list_id: int,
        user_id: int,
        source_module: Optional[str] = "general",
    ) -> bool:
        """Whether user can view a list."""
        return await self.get_access_role(list_id, user_id, source_module=source_module) in LIST_ROLES

    async def can_edit(
        self,
        list_id: int,
        user_id: int,
        source_module: Optional[str] = "general",
    ) -> bool:
        """Whether user can edit list items."""
        return await self.get_access_role(list_id, user_id, source_module=source_module) in EDIT_ROLES

    async def can_manage(
        self,
        list_id: int,
        user_id: int,
        source_module: Optional[str] = "general",
    ) -> bool:
        """Whether user owns and can manage the list itself."""
        return await self.get_access_role(list_id, user_id, source_module=source_module) == "owner"

    async def get_lists_list(
        self,
        user_id: int,
        page: int = 0,
        page_size: int = 10,
        source_module: str = "general",
    ) -> tuple[list[TodoList], int]:
        """Get paginated list of TodoLists."""
        offset = page * page_size

        lists = list(
            await self.repo.get_accessible_by_user(
                user_id,
                limit=page_size,
                offset=offset,
                source_module=source_module,
            )
        )
        total = await self.repo.count_accessible_by_user(user_id, source_module=source_module)
        for list_obj in lists:
            setattr(
                list_obj,
                "_access_role",
                await self.get_access_role(list_obj.id, user_id, source_module=source_module),
            )
        return lists, total

    async def get_list_items(
        self,
        list_id: int,
        user_id: int,
        source_module: Optional[str] = "general",
    ) -> list[ListItem]:
        """Get items for a TodoList if the user can view it."""
        if not await self.can_view(list_id, user_id, source_module=source_module):
            return []
        list_obj = await self.repo.get_with_items(list_id)
        if not list_obj or (source_module is not None and list_obj.source_module != source_module):
            return []
        items = await self.repo.get_items_for_user(list_id, list_obj.user_id)
        return list(items)

    async def get_item_by_id(
        self,
        item_id: int,
        user_id: int,
        source_module: Optional[str] = "general",
    ) -> Optional[ListItem]:
        """Get item by ID with access check."""
        result = await self.db.execute(select(ListItem).where(ListItem.id == item_id))
        item = result.scalar_one_or_none()
        if not item or not await self.can_view(item.list_id, user_id, source_module=source_module):
            return None
        return item

    async def update_list_title(
        self,
        list_id: int,
        user_id: int,
        new_title: str,
        source_module: Optional[str] = "general",
    ) -> Optional[TodoList]:
        """Rename a TodoList."""
        list_obj = await self.get_list(list_id, user_id, source_module=source_module)
        if not list_obj or not await self.can_manage(list_id, user_id, source_module=source_module):
            return None

        list_obj.title = new_title
        list_obj.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(list_obj)

        logger.info(f"Renamed TodoList {list_id} to '{new_title}'")
        return list_obj

    async def delete_list(
        self,
        list_id: int,
        user_id: int,
        source_module: Optional[str] = "general",
    ) -> bool:
        """Delete a TodoList (cascade deletes items)."""
        list_obj = await self.get_list(list_id, user_id, source_module=source_module)
        if not list_obj or not await self.can_manage(list_id, user_id, source_module=source_module):
            return False

        await self.db.delete(list_obj)
        await self.db.flush()

        logger.info(f"Deleted TodoList {list_id}")
        return True

    async def add_item(
        self,
        list_id: int,
        user_id: int,
        text: str,
        position: Optional[int] = None,
        source_module: Optional[str] = "general",
    ) -> Optional[ListItem]:
        """Add item to TodoList."""
        list_obj = await self.get_list(list_id, user_id, source_module=source_module)
        if not list_obj or not await self.can_edit(list_id, user_id, source_module=source_module):
            return None

        item = await self.repo.add_item(list_id, text, position)
        list_obj.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        logger.info(f"Added item {item.id} to TodoList {list_id}")
        return item

    async def add_items_bulk(
        self,
        list_id: int,
        user_id: int,
        texts: list[str],
        source_module: Optional[str] = "general",
    ) -> list[ListItem]:
        """Add multiple items to TodoList."""
        items = []
        for i, text in enumerate(texts):
            item = await self.add_item(
                list_id,
                user_id,
                text.strip(),
                position=i,
                source_module=source_module,
            )
            if item:
                items.append(item)

        logger.info(f"Added {len(items)} items to TodoList {list_id}")
        return items

    async def toggle_item(
        self,
        item_id: int,
        list_id: int,
        user_id: int,
    ) -> Optional[ListItem]:
        """Toggle item completion status."""
        if not await self.can_edit(list_id, user_id):
            return None
        item = await self.repo.get_item_in_list_for_user(item_id, list_id, (await self.repo.get_with_items(list_id)).user_id)
        if not item:
            return None

        item.is_completed = item.is_completed is not True
        list_obj = await self.get_list(list_id, user_id)
        if list_obj:
            list_obj.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(item)
        logger.info(f"Toggled item {item_id} in TodoList {list_id}")
        return item

    async def toggle_item_by_id(
        self,
        item_id: int,
        user_id: int,
        source_module: Optional[str] = "general",
    ) -> Optional[ListItem]:
        """Toggle item completion by item ID with ownership check."""
        item = await self.get_item_by_id(item_id, user_id, source_module=source_module)
        if not item or not await self.can_edit(item.list_id, user_id, source_module=source_module):
            return None

        item.is_completed = item.is_completed is not True
        await self.db.flush()
        await self.db.refresh(item)

        list_obj = await self.get_list(item.list_id, user_id, source_module=source_module)
        if list_obj:
            list_obj.updated_at = datetime.now(timezone.utc)
            await self.db.flush()

        logger.info(f"Toggled item {item_id}")
        return item

    async def update_item_text(
        self,
        item_id: int,
        list_id: int,
        user_id: int,
        new_text: str,
    ) -> Optional[ListItem]:
        """Update item text."""
        if not await self.can_edit(list_id, user_id):
            return None
        item = await self.repo.get_item_in_list_for_user(item_id, list_id, (await self.repo.get_with_items(list_id)).user_id)
        if not item:
            return None

        item.text = new_text
        list_obj = await self.get_list(list_id, user_id)
        if list_obj:
            list_obj.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(item)
        logger.info(f"Updated item {item_id}")

        return item

    async def update_item_text_by_id(
        self,
        item_id: int,
        user_id: int,
        new_text: str,
        source_module: Optional[str] = "general",
    ) -> Optional[ListItem]:
        """Update item text by item ID with ownership check."""
        item = await self.get_item_by_id(item_id, user_id, source_module=source_module)
        if not item or not await self.can_edit(item.list_id, user_id, source_module=source_module):
            return None

        item.text = new_text
        await self.db.flush()
        await self.db.refresh(item)

        list_obj = await self.get_list(item.list_id, user_id, source_module=source_module)
        if list_obj:
            list_obj.updated_at = datetime.now(timezone.utc)
            await self.db.flush()

        logger.info(f"Updated item {item_id}")
        return item

    async def delete_item(
        self,
        item_id: int,
        list_id: int,
        user_id: int,
    ) -> bool:
        """Delete item from TodoList."""
        if not await self.can_edit(list_id, user_id):
            return False
        item = await self.repo.get_item_in_list_for_user(item_id, list_id, (await self.repo.get_with_items(list_id)).user_id)
        if not item:
            return False

        list_obj = await self.get_list(list_id, user_id)
        await self.db.delete(item)
        if list_obj:
            list_obj.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        logger.info(f"Deleted item {item_id} from TodoList {list_id}")
        return True

    async def delete_item_by_id(
        self,
        item_id: int,
        user_id: int,
        source_module: Optional[str] = "general",
    ) -> bool:
        """Delete item by item ID with ownership check."""
        item = await self.get_item_by_id(item_id, user_id, source_module=source_module)
        if not item or not await self.can_edit(item.list_id, user_id, source_module=source_module):
            return False

        list_id = item.list_id
        await self.db.delete(item)

        list_obj = await self.get_list(list_id, user_id, source_module=source_module)
        if list_obj:
            list_obj.updated_at = datetime.now(timezone.utc)

        await self.db.flush()
        logger.info(f"Deleted item {item_id} from TodoList {list_id}")
        return True

    async def get_item(
        self,
        item_id: int,
        list_id: int,
        user_id: int,
    ) -> Optional[ListItem]:
        """Get item by ID."""
        list_obj = await self.get_list(list_id, user_id)
        if not list_obj:
            return None

        return await self.repo.get_item_in_list_for_user(item_id, list_id, list_obj.user_id)

    async def format_list_as_text(
        self,
        list_id: int,
        user_id: int,
        source_module: Optional[str] = "general",
    ) -> Optional[str]:
        """Format TodoList with items as plain text for copying."""
        list_obj = await self.get_list(list_id, user_id, source_module=source_module)
        if not list_obj:
            return None

        items = await self.get_list_items(list_id, user_id, source_module=source_module)

        lines = [f"📋 {list_obj.title}"]
        if items:
            lines.append("")

        for i, item in enumerate(items, 1):
            status = "✅" if item.is_completed else "⬜"
            lines.append(f"{i}. {status} {item.text}")

        return "\n".join(lines)

    async def create_share_token(
        self,
        list_id: int,
        user_id: int,
        expires_in_days: int = 7,
        max_uses: int = 20,
    ) -> Optional[ListShareToken]:
        """Create a token that lets another user copy this list."""
        if not await self.can_manage(list_id, user_id):
            return None

        token = secrets.token_urlsafe(12)
        share = ListShareToken(
            token=token,
            list_id=list_id,
            created_by_user_id=user_id,
            token_type="copy",
            access_role="viewer",
            expires_at_utc=datetime.now(timezone.utc) + timedelta(days=expires_in_days),
            max_uses=max_uses,
            uses_count=0,
            is_active=True,
        )
        self.db.add(share)
        await self.db.flush()
        await self.db.refresh(share)
        return share

    async def create_collaboration_token(
        self,
        list_id: int,
        user_id: int,
        role: str = "editor",
        expires_in_days: int = 7,
        max_uses: int = 20,
    ) -> Optional[ListShareToken]:
        """Create a token that lets another user join the same list."""
        if role not in {"editor", "viewer"}:
            role = "viewer"
        if not await self.can_manage(list_id, user_id):
            return None

        token = secrets.token_urlsafe(12)
        share = ListShareToken(
            token=token,
            list_id=list_id,
            created_by_user_id=user_id,
            token_type="collab",
            access_role=role,
            expires_at_utc=datetime.now(timezone.utc) + timedelta(days=expires_in_days),
            max_uses=max_uses,
            uses_count=0,
            is_active=True,
        )
        self.db.add(share)
        await self.db.flush()
        await self.db.refresh(share)
        return share

    async def join_shared_list(self, token: str, recipient_user_id: int) -> Optional[TodoList]:
        """Join an existing shared list using a collaboration token."""
        result = await self.db.execute(
            select(ListShareToken).where(ListShareToken.token == token.strip())
        )
        share = result.scalar_one_or_none()
        now = datetime.now(timezone.utc)
        expires_at = share.expires_at_utc if share else None
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if (
            not share
            or not share.is_active
            or share.token_type != "collab"
            or expires_at < now
            or share.uses_count >= share.max_uses
        ):
            return None

        source = await self.repo.get_with_items(share.list_id)
        if not source:
            share.is_active = False
            await self.db.flush()
            return None
        if source.user_id == recipient_user_id:
            return source

        existing = await self.get_access_role(source.id, recipient_user_id)
        if existing:
            return source

        member = ListMember(
            list_id=source.id,
            user_id=recipient_user_id,
            role=share.access_role if share.access_role in {"editor", "viewer"} else "viewer",
            invited_by_user_id=share.created_by_user_id,
        )
        self.db.add(member)
        share.uses_count += 1
        await self.db.flush()
        await self.db.refresh(source)
        return source

    async def get_list_members(
        self,
        list_id: int,
        owner_user_id: int,
    ) -> Optional[list[dict]]:
        """Return list owner and members for owner management UI."""
        if not await self.can_manage(list_id, owner_user_id):
            return None

        list_obj = await self.repo.get_with_items(list_id)
        if not list_obj:
            return None

        owner_result = await self.db.execute(select(User).where(User.id == list_obj.user_id))
        owner = owner_result.scalar_one_or_none()

        result = await self.db.execute(
            select(ListMember)
            .options(selectinload(ListMember.user))
            .where(ListMember.list_id == list_id)
            .order_by(ListMember.created_at.asc(), ListMember.id.asc())
        )
        members = result.scalars().all()

        def display_name(user: Optional[User]) -> str:
            if not user:
                return "Пользователь"
            if user.username:
                return f"@{user.username}"
            full_name = " ".join(part for part in [user.first_name, user.last_name] if part)
            return full_name or f"id {user.telegram_id}"

        rows = [
            {
                "member_id": None,
                "user_id": owner.id if owner else list_obj.user_id,
                "role": "owner",
                "display_name": display_name(owner),
            }
        ]
        for member in members:
            rows.append(
                {
                    "member_id": member.id,
                    "user_id": member.user_id,
                    "role": member.role,
                    "display_name": display_name(member.user),
                }
            )
        return rows

    async def update_member_role(
        self,
        list_id: int,
        owner_user_id: int,
        member_id: int,
        role: str,
    ) -> Optional[ListMember]:
        """Change a shared list member role. Only owner can do it."""
        if role not in {"editor", "viewer"}:
            return None
        if not await self.can_manage(list_id, owner_user_id):
            return None

        result = await self.db.execute(
            select(ListMember).where(
                and_(
                    ListMember.id == member_id,
                    ListMember.list_id == list_id,
                )
            )
        )
        member = result.scalar_one_or_none()
        if not member:
            return None

        member.role = role
        await self.db.flush()
        await self.db.refresh(member)
        return member

    async def remove_member(
        self,
        list_id: int,
        owner_user_id: int,
        member_id: int,
    ) -> bool:
        """Revoke a shared list member access. Only owner can do it."""
        if not await self.can_manage(list_id, owner_user_id):
            return False

        result = await self.db.execute(
            select(ListMember).where(
                and_(
                    ListMember.id == member_id,
                    ListMember.list_id == list_id,
                )
            )
        )
        member = result.scalar_one_or_none()
        if not member:
            return False

        await self.db.delete(member)
        await self.db.flush()
        return True

    async def import_shared_list(
        self,
        token: str,
        recipient_user_id: int,
    ) -> Optional[TodoList]:
        """Copy a shared list into the recipient's account."""
        result = await self.db.execute(
            select(ListShareToken).where(ListShareToken.token == token.strip())
        )
        share = result.scalar_one_or_none()
        now = datetime.now(timezone.utc)
        expires_at = share.expires_at_utc if share else None
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if (
            not share
            or not share.is_active
            or share.token_type != "copy"
            or expires_at < now
            or share.uses_count >= share.max_uses
        ):
            return None

        source = await self.get_list(share.list_id, share.created_by_user_id)
        if not source:
            share.is_active = False
            await self.db.flush()
            return None

        new_list = await self.create_list(
            user_id=recipient_user_id,
            title=f"{source.title} (копия)",
            source_module=source.source_module,
        )
        items = await self.get_list_items(source.id, share.created_by_user_id)
        for item in items:
            new_item = await self.add_item(
                list_id=new_list.id,
                user_id=recipient_user_id,
                text=item.text,
                position=item.position,
            )
            if new_item:
                new_item.is_completed = item.is_completed

        share.uses_count += 1
        await self.db.flush()
        await self.db.refresh(new_list)
        return new_list
