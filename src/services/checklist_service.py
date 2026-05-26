"""Service for personal interactive checklist executions."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models import ChecklistRun, ChecklistRunItem, TodoList
from src.services.list_service import ListService


ACTIVE = "active"
COMPLETED = "completed"
CANCELED = "canceled"


class ChecklistService:
    """Business logic for running a list as a temporary checklist."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.list_service = ListService(db)

    async def create_run_from_list(
        self,
        list_id: int,
        user_id: int,
        source_module: Optional[str] = None,
    ) -> Optional[ChecklistRun]:
        """Create a personal checklist run snapshot from an accessible list."""
        list_obj = await self.list_service.get_list(list_id, user_id, source_module=source_module)
        if not list_obj:
            return None

        items = await self.list_service.get_list_items(list_id, user_id, source_module=source_module)
        if not items:
            return None

        run = ChecklistRun(
            user_id=user_id,
            source_list_id=list_obj.id,
            title_snapshot=list_obj.title,
            source_updated_at=list_obj.updated_at,
            status=ACTIVE,
        )
        self.db.add(run)
        await self.db.flush()

        for index, item in enumerate(items):
            self.db.add(
                ChecklistRunItem(
                    run_id=run.id,
                    source_item_id=item.id,
                    text_snapshot=item.text,
                    position=item.position if item.position is not None else index,
                    checked=False,
                )
            )

        await self.db.flush()
        return await self.get_run(run.id, user_id)

    async def get_run(self, run_id: int, user_id: int) -> Optional[ChecklistRun]:
        """Return a checklist run owned by the current user."""
        result = await self.db.execute(
            select(ChecklistRun)
            .options(selectinload(ChecklistRun.items), selectinload(ChecklistRun.source_list))
            .where(ChecklistRun.id == run_id, ChecklistRun.user_id == user_id)
        )
        return result.scalars().unique().one_or_none()

    async def toggle_item(
        self,
        run_id: int,
        item_id: int,
        user_id: int,
    ) -> Optional[ChecklistRun]:
        """Toggle a snapshot item inside an active checklist run."""
        run = await self.get_run(run_id, user_id)
        if not run or run.status != ACTIVE:
            return None

        item = next((item for item in run.items if item.id == item_id), None)
        if not item:
            return None

        item.checked = item.checked is not True
        run.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return await self.get_run(run_id, user_id)

    async def check_all(self, run_id: int, user_id: int) -> Optional[ChecklistRun]:
        """Mark all items checked for an active checklist run."""
        run = await self.get_run(run_id, user_id)
        if not run or run.status != ACTIVE:
            return None

        for item in run.items:
            item.checked = True
        run.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return await self.get_run(run_id, user_id)

    async def finish_run(self, run_id: int, user_id: int) -> Optional[ChecklistRun]:
        """Complete an active checklist run if every snapshot item is checked."""
        run = await self.get_run(run_id, user_id)
        if not run or run.status != ACTIVE or not self.all_checked(run):
            return None

        now = datetime.now(timezone.utc)
        run.status = COMPLETED
        run.completed_at = now
        run.updated_at = now
        await self.db.flush()
        return await self.get_run(run_id, user_id)

    async def cancel_run(self, run_id: int, user_id: int) -> Optional[ChecklistRun]:
        """Cancel an active checklist run."""
        run = await self.get_run(run_id, user_id)
        if not run or run.status != ACTIVE:
            return None

        run.status = CANCELED
        run.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return await self.get_run(run_id, user_id)

    async def source_changed(self, run: ChecklistRun) -> bool:
        """Return whether the source list changed after the run snapshot."""
        if not run.source_list_id or not run.source_updated_at:
            return False

        result = await self.db.execute(select(TodoList).where(TodoList.id == run.source_list_id))
        source = result.scalar_one_or_none()
        if not source:
            return True

        return _normalize_dt(source.updated_at) != _normalize_dt(run.source_updated_at)

    @staticmethod
    def all_checked(run: ChecklistRun) -> bool:
        """Return whether every snapshot item is checked."""
        return bool(run.items) and all(item.checked for item in run.items)

    @staticmethod
    def progress(run: ChecklistRun) -> tuple[int, int]:
        """Return checked and total item counts."""
        total = len(run.items)
        checked = sum(1 for item in run.items if item.checked)
        return checked, total


def _normalize_dt(value: datetime | None) -> datetime | None:
    """Normalize DB datetimes for stable equality checks across dialects."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(microsecond=0)
