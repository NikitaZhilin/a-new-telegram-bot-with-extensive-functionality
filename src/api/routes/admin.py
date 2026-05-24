"""
Admin routes.

All endpoints require X-Admin-Token header for authentication.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_admin
from src.db.session import get_db
from src.db.models import Medication, Note, TodoList, Reminder, ReminderStatus, User
from src.services.driver_service import DriverService
from src.services.subscription_service import SubscriptionService

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[require_admin])


# === Response Models ===

class UserResponse(BaseModel):
    """User information."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: int
    username: Optional[str]
    first_name: Optional[str]
    timezone: str
    is_admin: bool
    onboarding_source: Optional[str]
    created_at: datetime


class UsersListResponse(BaseModel):
    """Paginated users list."""
    users: List[UserResponse]
    total: int
    page: int
    page_size: int


class StatsCount(BaseModel):
    """Simple count statistic."""
    total: int
    created_today: int
    created_week: int


class StatsReminders(BaseModel):
    """Reminder statistics with status breakdown."""
    total: int
    active: int
    done: int
    canceled: int
    missed: int
    due_soon: int  # Due in next hour


class StatsResponse(BaseModel):
    """System statistics."""
    users: StatsCount
    notes: StatsCount
    lists: StatsCount
    reminders: StatsReminders
    generated_at: str


class UserRecordsResponse(BaseModel):
    """Admin support overview for one user's isolated records."""

    user: UserResponse
    access: dict
    lists: List[dict]
    reminders: List[dict]
    medications: List[dict]
    driver: dict


# === Routes ===

@router.get(
    "/users",
    response_model=UsersListResponse,
    summary="Get all users",
    description="Get paginated list of all users (admin only)",
)
async def get_users(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
) -> UsersListResponse:
    """
    Get paginated list of all users.
    
    Requires X-Admin-Token header.
    
    Args:
        page: Page number (1-indexed)
        page_size: Items per page (1-100)
        db: Database session
        
    Returns:
        Paginated list of users with total count
    """
    offset = (page - 1) * page_size
    
    # Get total count
    count_query = select(func.count(User.id))
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # Get users
    query = (
        select(User)
        .order_by(User.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    
    result = await db.execute(query)
    users = result.scalars().all()
    
    return UsersListResponse(
        users=[UserResponse.model_validate(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/users/{user_id}",
    response_model=UserResponse,
    summary="Get user by ID",
    description="Get detailed information about a specific user (admin only)",
)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """
    Get user by ID.
    
    Args:
        user_id: User ID
        db: Database session
        
    Returns:
        User information
        
    Raises:
        404: User not found
    """
    query = select(User).where(User.id == user_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )
    
    return UserResponse.model_validate(user)


@router.get(
    "/users/{user_id}/records",
    response_model=UserRecordsResponse,
    summary="Get user records overview",
    description="Admin-only support view of one user's isolated records",
)
async def get_user_records(
    user_id: int,
    db: AsyncSession = Depends(get_db),
) -> UserRecordsResponse:
    """Get a compact support overview of one user's records."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )

    subscription_service = SubscriptionService(db)
    access = await subscription_service.get_access_context(user_id)
    driver_service = DriverService(db)
    driver_overview = await driver_service.get_user_overview(user_id)

    lists_result = await db.execute(
        select(TodoList)
        .where(TodoList.user_id == user_id)
        .order_by(TodoList.updated_at.desc())
        .limit(50)
    )
    reminders_result = await db.execute(
        select(Reminder)
        .where(Reminder.user_id == user_id)
        .order_by(Reminder.remind_at_utc.desc())
        .limit(50)
    )
    medications_result = await db.execute(
        select(Medication)
        .where(Medication.user_id == user_id)
        .order_by(Medication.updated_at.desc())
        .limit(50)
    )
    lists = lists_result.scalars().all()
    reminders = reminders_result.scalars().all()
    medications = medications_result.scalars().all()
    vehicles = await driver_service.get_vehicles(user_id)

    return UserRecordsResponse(
        user=UserResponse.model_validate(user),
        access=access,
        lists=[
            {
                "id": item.id,
                "title": item.title,
                "created_at": item.created_at.isoformat(),
                "updated_at": item.updated_at.isoformat(),
            }
            for item in lists
        ],
        reminders=[
            {
                "id": item.id,
                "title": item.title,
                "status": item.status.value if hasattr(item.status, "value") else item.status,
                "remind_at_utc": item.remind_at_utc.isoformat(),
                "text": item.text[:200],
            }
            for item in reminders
        ],
        medications=[
            {
                "id": item.id,
                "name": item.name,
                "importance": item.importance,
                "is_active": item.is_active,
                "updated_at": item.updated_at.isoformat(),
            }
            for item in medications
        ],
        driver={
            "overview": driver_overview,
            "vehicles": [
                {
                    "id": vehicle.id,
                    "title": vehicle.title,
                    "current_mileage_km": vehicle.current_mileage_km,
                    "manual_mileage_km": vehicle.manual_mileage_km,
                    "service_interval_km": vehicle.service_interval_km,
                    "service_interval_months": vehicle.service_interval_months,
                    "updated_at": vehicle.updated_at.isoformat(),
                }
                for vehicle in vehicles[:50]
            ],
        },
    )


@router.get(
    "/stats",
    response_model=StatsResponse,
    summary="Get system statistics",
    description="Get comprehensive system statistics (admin only)",
)
async def get_stats(
    db: AsyncSession = Depends(get_db),
) -> StatsResponse:
    """
    Get system statistics.
    
    Includes counts for users, notes, lists, and reminders with status breakdown.
    
    Args:
        db: Database session
        
    Returns:
        System statistics
    """
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Helper to get count with optional date filter
    async def get_count(model, since: Optional[datetime] = None) -> int:
        query = select(func.count(model.id))
        if since:
            query = query.where(model.created_at >= since)
        result = await db.execute(query)
        return result.scalar() or 0
    
    # Get basic counts
    users_total = await get_count(User)
    users_today = await get_count(User, today_start)
    users_week = await get_count(User, week_start)
    
    notes_total = await get_count(Note)
    notes_today = await get_count(Note, today_start)
    notes_week = await get_count(Note, week_start)
    
    lists_total = await get_count(TodoList)
    lists_today = await get_count(TodoList, today_start)
    lists_week = await get_count(TodoList, week_start)
    
    # Reminder counts by status
    from sqlalchemy import and_
    
    reminders_total = await get_count(Reminder)
    
    # Count by status
    async def count_by_status(s: ReminderStatus) -> int:
        query = select(func.count(Reminder.id)).where(Reminder.status == s)
        result = await db.execute(query)
        return result.scalar() or 0
    
    reminders_active = await count_by_status(ReminderStatus.ACTIVE)
    reminders_done = await count_by_status(ReminderStatus.DONE)
    reminders_canceled = await count_by_status(ReminderStatus.CANCELED)
    reminders_missed = await count_by_status(ReminderStatus.MISSED)
    
    # Due soon (active, not notified, due in next hour)
    from datetime import timedelta
    one_hour_later = now + timedelta(hours=1)
    
    due_soon_query = (
        select(func.count(Reminder.id))
        .where(
            and_(
                Reminder.status == ReminderStatus.ACTIVE,
                Reminder.remind_at_utc <= one_hour_later,
                Reminder.notified_at.is_(None),
            )
        )
    )
    result = await db.execute(due_soon_query)
    reminders_due_soon = result.scalar() or 0
    
    return StatsResponse(
        users=StatsCount(
            total=users_total,
            created_today=users_today,
            created_week=users_week,
        ),
        notes=StatsCount(
            total=notes_total,
            created_today=notes_today,
            created_week=notes_week,
        ),
        lists=StatsCount(
            total=lists_total,
            created_today=lists_today,
            created_week=lists_week,
        ),
        reminders=StatsReminders(
            total=reminders_total,
            active=reminders_active,
            done=reminders_done,
            canceled=reminders_canceled,
            missed=reminders_missed,
            due_soon=reminders_due_soon,
        ),
        generated_at=now.isoformat(),
    )


@router.get(
    "/reminders/due",
    summary="Get due reminders",
    description="Get reminders that are due soon (admin only)",
)
async def get_due_reminders(
    limit: int = Query(50, ge=1, le=200, description="Max reminders to return"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get reminders that are due or overdue.
    
    Args:
        limit: Maximum number of reminders (1-200)
        db: Database session
        
    Returns:
        List of due reminders
    """
    from datetime import timedelta
    from sqlalchemy import and_
    
    now = datetime.now(timezone.utc)
    one_hour_later = now + timedelta(hours=1)
    
    query = (
        select(Reminder)
        .where(
            and_(
                Reminder.status == ReminderStatus.ACTIVE,
                Reminder.remind_at_utc <= one_hour_later,
                Reminder.notified_at.is_(None),
            )
        )
        .order_by(Reminder.remind_at_utc.asc())
        .limit(limit)
    )
    
    result = await db.execute(query)
    reminders = result.scalars().all()
    
    return {
        "reminders": [
            {
                "id": r.id,
                "user_id": r.user_id,
                "text": r.text[:100] + "..." if len(r.text) > 100 else r.text,
                "remind_at_utc": r.remind_at_utc.isoformat(),
                "repeat_rule": r.repeat_rule.value,
            }
            for r in reminders
        ],
        "count": len(reminders),
        "generated_at": now.isoformat(),
    }
