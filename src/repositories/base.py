"""Base repository."""

from typing import TypeVar, Generic, Type, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete

from src.db.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Base repository for CRUD operations."""
    
    def __init__(self, model: Type[ModelType], db: AsyncSession):
        self.model = model
        self.db = db
    
    async def get(self, id: int) -> Optional[ModelType]:
        """Get by ID."""
        result = await self.db.execute(select(self.model).where(self.model.id == id))
        return result.scalar_one_or_none()
    
    async def get_multi(self, skip: int = 0, limit: int = 100) -> List[ModelType]:
        """Get multiple records."""
        result = await self.db.execute(select(self.model).offset(skip).limit(limit))
        return result.scalars().all()
    
    async def create(self, obj_in: dict) -> ModelType:
        """Create new record."""
        obj_in_db = self.model(**obj_in)
        self.db.add(obj_in_db)
        await self.db.flush()
        await self.db.refresh(obj_in_db)
        return obj_in_db
    
    async def update(self, db_obj: ModelType, obj_in: dict) -> ModelType:
        """Update record."""
        for field, value in obj_in.items():
            setattr(db_obj, field, value)
        await self.db.flush()
        await self.db.refresh(db_obj)
        return db_obj
    
    async def delete(self, id: int) -> None:
        """Delete by ID."""
        await self.db.execute(delete(self.model).where(self.model.id == id))
