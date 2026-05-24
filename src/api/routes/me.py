"""User-scoped API for future web/PWA clients."""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.user_auth import get_current_web_user
from src.db.models import DriverVehicle, Medication, Reminder, ReminderStatus, TodoList, User
from src.db.session import get_db
from src.services.driver_service import DriverService
from src.services.settings_service import SettingsService
from src.services.subscription_service import SubscriptionService


router = APIRouter()


class MeResponse(BaseModel):
    """Current user profile."""

    id: int
    telegram_id: int
    username: Optional[str]
    first_name: Optional[str]
    timezone: str
    is_admin: bool
    created_at: datetime


class MeSummaryResponse(BaseModel):
    """Compact summary for a future web/PWA dashboard."""

    user: MeResponse
    stats: dict
    access: dict


class ListSummaryResponse(BaseModel):
    """Todo list summary."""

    id: int
    title: str
    source_module: str
    items_total: int
    items_done: int
    updated_at: datetime


class ReminderSummaryResponse(BaseModel):
    """Reminder summary."""

    id: int
    title: Optional[str]
    text: str
    source_module: str
    status: str
    remind_at_utc: datetime
    repeat_rule: str


class MedicationSummaryResponse(BaseModel):
    """Medication summary."""

    id: int
    name: str
    dosage: Optional[str]
    instructions: Optional[str]
    importance: str
    is_active: bool
    updated_at: datetime


class DriverVehicleSummaryResponse(BaseModel):
    """Vehicle summary."""

    id: int
    title: str
    current_mileage_km: int
    service_interval_km: int
    service_interval_months: int
    updated_at: datetime


class DriverDashboardResponse(BaseModel):
    """Driver dashboard summary."""

    overview: dict
    vehicles: List[DriverVehicleSummaryResponse]


def _user_response(user: User) -> MeResponse:
    """Serialize User ORM object."""
    return MeResponse(
        id=user.id,
        telegram_id=user.telegram_id,
        username=user.username,
        first_name=user.first_name,
        timezone=user.timezone,
        is_admin=user.is_admin,
        created_at=user.created_at,
    )


@router.get("/me", response_model=MeResponse)
async def get_me(current_user: User = Depends(get_current_web_user)) -> MeResponse:
    """Return current authenticated user."""
    return _user_response(current_user)


@router.get("/me/summary", response_model=MeSummaryResponse)
async def get_me_summary(
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> MeSummaryResponse:
    """Return compact dashboard data."""
    stats = await SettingsService(db).get_stats(current_user.id)
    access = await SubscriptionService(db).get_access_context(current_user.id)
    return MeSummaryResponse(
        user=_user_response(current_user),
        stats=stats,
        access=access,
    )


@router.get("/me/lists", response_model=List[ListSummaryResponse])
async def get_my_lists(
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> List[ListSummaryResponse]:
    """Return current user's generic lists."""
    result = await db.execute(
        select(TodoList)
        .options(selectinload(TodoList.items))
        .where(TodoList.user_id == current_user.id, TodoList.source_module == "general")
        .order_by(TodoList.updated_at.desc(), TodoList.id.desc())
        .limit(limit)
    )
    lists = result.scalars().unique().all()
    return [
        ListSummaryResponse(
            id=item.id,
            title=item.title,
            source_module=item.source_module,
            items_total=len(item.items),
            items_done=sum(1 for list_item in item.items if list_item.is_completed),
            updated_at=item.updated_at,
        )
        for item in lists
    ]


@router.get("/me/reminders", response_model=List[ReminderSummaryResponse])
async def get_my_reminders(
    active_only: bool = Query(True),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> List[ReminderSummaryResponse]:
    """Return current user's generic reminders."""
    conditions = [
        Reminder.user_id == current_user.id,
        Reminder.source_module == "general",
    ]
    if active_only:
        conditions.append(Reminder.status == ReminderStatus.ACTIVE)
    result = await db.execute(
        select(Reminder)
        .where(*conditions)
        .order_by(Reminder.remind_at_utc.asc())
        .limit(limit)
    )
    reminders = result.scalars().all()
    return [
        ReminderSummaryResponse(
            id=item.id,
            title=item.title,
            text=item.text,
            source_module=item.source_module,
            status=item.status.value if hasattr(item.status, "value") else item.status,
            remind_at_utc=item.remind_at_utc,
            repeat_rule=item.repeat_rule.value if hasattr(item.repeat_rule, "value") else item.repeat_rule,
        )
        for item in reminders
    ]


@router.get("/me/medications", response_model=List[MedicationSummaryResponse])
async def get_my_medications(
    active_only: bool = Query(True),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> List[MedicationSummaryResponse]:
    """Return current user's medications."""
    conditions = [Medication.user_id == current_user.id]
    if active_only:
        conditions.append(Medication.is_active.is_(True))
    result = await db.execute(
        select(Medication)
        .where(*conditions)
        .order_by(Medication.updated_at.desc(), Medication.id.desc())
        .limit(limit)
    )
    medications = result.scalars().all()
    return [
        MedicationSummaryResponse(
            id=item.id,
            name=item.name,
            dosage=item.dosage,
            instructions=item.instructions,
            importance=item.importance,
            is_active=item.is_active,
            updated_at=item.updated_at,
        )
        for item in medications
    ]


@router.get("/me/driver", response_model=DriverDashboardResponse)
async def get_my_driver_dashboard(
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> DriverDashboardResponse:
    """Return current user's driver dashboard."""
    driver_service = DriverService(db)
    overview = await driver_service.get_user_overview(current_user.id)
    vehicles_result = await db.execute(
        select(DriverVehicle)
        .where(DriverVehicle.user_id == current_user.id)
        .order_by(DriverVehicle.updated_at.desc(), DriverVehicle.id.desc())
        .limit(50)
    )
    vehicles = vehicles_result.scalars().all()
    return DriverDashboardResponse(
        overview=overview,
        vehicles=[
            DriverVehicleSummaryResponse(
                id=item.id,
                title=item.title,
                current_mileage_km=item.current_mileage_km,
                service_interval_km=item.service_interval_km,
                service_interval_months=item.service_interval_months,
                updated_at=item.updated_at,
            )
            for item in vehicles
        ],
    )
