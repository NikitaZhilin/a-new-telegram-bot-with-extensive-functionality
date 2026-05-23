"""Medication repository."""

from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models import Medication, MedicationIntake, MedicationIntakeStatus
from src.repositories.base import BaseRepository


class MedicationRepository(BaseRepository[Medication]):
    """Repository for user medication schedules."""

    def __init__(self, db: AsyncSession):
        super().__init__(Medication, db)

    async def get_by_user(
        self,
        user_id: int,
        active: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Medication]:
        """Get medications for one user."""
        query = (
            select(Medication)
            .where(
                and_(
                    Medication.user_id == user_id,
                    Medication.is_active.is_(active),
                )
            )
            .order_by(Medication.updated_at.desc(), Medication.id.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_by_user(self, user_id: int, active: bool = True) -> int:
        """Count medications for one user."""
        query = select(func.count(Medication.id)).where(
            and_(
                Medication.user_id == user_id,
                Medication.is_active.is_(active),
            )
        )
        result = await self.db.execute(query)
        return result.scalar() or 0

    async def get_for_user(self, medication_id: int, user_id: int) -> Optional[Medication]:
        """Get one medication with ownership check."""
        query = (
            select(Medication)
            .options(selectinload(Medication.intakes))
            .where(
                and_(
                    Medication.id == medication_id,
                    Medication.user_id == user_id,
                )
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_intakes_for_user(
        self,
        medication_id: int,
        user_id: int,
        limit: int = 5,
    ) -> Sequence[MedicationIntake]:
        """Get recent intake marks with ownership check."""
        query = (
            select(MedicationIntake)
            .join(Medication, Medication.id == MedicationIntake.medication_id)
            .where(
                and_(
                    MedicationIntake.medication_id == medication_id,
                    MedicationIntake.user_id == user_id,
                    Medication.user_id == user_id,
                )
            )
            .order_by(MedicationIntake.taken_at_utc.desc())
            .limit(limit)
        )
        result = await self.db.execute(query)
        return result.scalars().all()

    async def add_intake(
        self,
        medication_id: int,
        user_id: int,
        taken_at_utc: datetime,
        status: MedicationIntakeStatus = MedicationIntakeStatus.TAKEN,
        note: Optional[str] = None,
    ) -> MedicationIntake:
        """Add one medication intake mark."""
        intake = MedicationIntake(
            medication_id=medication_id,
            user_id=user_id,
            taken_at_utc=taken_at_utc,
            status=status,
            note=note,
        )
        self.db.add(intake)
        await self.db.flush()
        await self.db.refresh(intake)
        return intake
