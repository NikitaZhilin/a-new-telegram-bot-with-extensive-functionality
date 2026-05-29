"""
Admin routes.

All endpoints require X-Admin-Token header for authentication.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, List, Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_admin
from src.db.session import get_db
from src.db.models import Medication, Note, TodoList, Reminder, ReminderStatus, User
from src.services.activity_service import ActivityService
from src.services.driver_service import DriverService
from src.services.restart_request_service import (
    RESTART_CONFIRMATION,
    RestartRequestNotSupportedError,
    RestartRequestService,
)
from src.services.service_heartbeat import ServiceStatusService
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
    lists: StatsCount
    notes: StatsCount
    reminders: StatsReminders
    generated_at: str


class UserRecordsResponse(BaseModel):
    """Admin support overview for one user's isolated records."""

    user: UserResponse
    access: dict
    lists: List[dict]
    notes: List[dict]
    reminders: List[dict]
    medications: List[dict]
    driver: dict


class ActivitySummaryResponse(BaseModel):
    """Sanitized behavior analytics summary."""

    period_days: int
    filtered_user_id: Optional[int] = None
    events_24h: int
    events_period: int
    active_other_users_24h: int
    active_other_users_period: int
    top_domains: List[dict]
    top_actions: List[dict]


class FunnelSummaryResponse(BaseModel):
    """Product funnel summary."""

    period_days: int
    filtered_user_id: Optional[int] = None
    funnels: List[dict]


class ServiceHeartbeatResponse(BaseModel):
    """Computed runtime heartbeat status for one service."""

    service_name: str
    status: str
    reported_status: Optional[str] = None
    required: bool
    stale: bool
    seconds_since_seen: Optional[int] = None
    version: Optional[str] = None
    started_at: Optional[str] = None
    last_seen_at: Optional[str] = None
    uptime_seconds: int
    last_error: Optional[str] = None
    metadata_json: dict[str, Any]


class ServiceStatusResponse(BaseModel):
    """Read-only service status snapshot for external status bots."""

    status: str
    version: str
    generated_at: str
    database: str
    last_errors_count: int
    heartbeat_down_after_seconds: int
    services: dict[str, ServiceHeartbeatResponse]


class RestartRequestPayload(BaseModel):
    """Controlled restart request accepted from an external status bot."""

    target: Literal["api", "bot", "worker", "all"]
    confirm: str = Field(..., min_length=1, max_length=80)
    requested_by: str = Field(..., min_length=1, max_length=120)
    reason: Optional[str] = Field(default=None, max_length=500)


class RestartAcceptedResponse(BaseModel):
    """Accepted restart request metadata."""

    status: str
    operation_id: str
    target: str
    message: str


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
    driver_expenses = await driver_service.get_expenses(user_id, limit=50)
    driver_documents = await driver_service.get_documents(user_id, active_only=False, limit=50)

    lists_result = await db.execute(
        select(TodoList)
        .where(TodoList.user_id == user_id)
        .order_by(TodoList.updated_at.desc())
        .limit(50)
    )
    notes_result = await db.execute(
        select(Note)
        .where(Note.user_id == user_id, Note.is_archived.is_not(True))
        .order_by(Note.updated_at.desc())
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
    notes = notes_result.scalars().all()
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
        notes=[
            {
                "id": item.id,
                "title": item.title,
                "category": item.category or "other",
                "text": (item.text or "")[:500],
                "created_at": item.created_at.isoformat(),
                "updated_at": item.updated_at.isoformat(),
            }
            for item in notes
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
            "expenses": [
                {
                    "id": expense.id,
                    "vehicle_id": expense.vehicle_id,
                    "title": expense.title,
                    "category": expense.category,
                    "amount": expense.amount,
                    "spent_at_utc": expense.spent_at_utc.isoformat(),
                }
                for expense in driver_expenses
            ],
            "documents": [
                {
                    "id": document.id,
                    "vehicle_id": document.vehicle_id,
                    "title": document.title,
                    "document_type": document.document_type,
                    "expires_at_utc": document.expires_at_utc.isoformat() if document.expires_at_utc else None,
                    "is_active": document.is_active,
                }
                for document in driver_documents
            ],
        },
    )


@router.get(
    "/activity",
    response_model=ActivitySummaryResponse,
    summary="Get bot activity summary",
    description="Admin-only privacy-safe interaction analytics",
)
async def get_activity_summary(
    current_user_id: int = Query(0, ge=0, description="Internal admin user ID to exclude from active-other-user counts"),
    days: int = Query(7, ge=1, le=30, description="Lookback period in days"),
    user_id: Optional[int] = Query(None, ge=1, description="Optional user ID filter"),
    db: AsyncSession = Depends(get_db),
) -> ActivitySummaryResponse:
    """Return sanitized aggregate activity without message text."""
    summary = await ActivityService(db).get_admin_event_summary(
        current_user_id=current_user_id,
        days=days,
        user_id=user_id,
    )
    return ActivitySummaryResponse(**summary)


@router.get(
    "/funnels",
    response_model=FunnelSummaryResponse,
    summary="Get product funnels",
    description="Admin-only funnel overview built from sanitized activity analytics",
)
async def get_funnel_summary(
    days: int = Query(7, ge=1, le=30, description="Lookback period in days"),
    user_id: Optional[int] = Query(None, ge=1, description="Optional user ID filter"),
    db: AsyncSession = Depends(get_db),
) -> FunnelSummaryResponse:
    """Return basic funnel stages for core bot domains."""
    summary = await ActivityService(db).get_funnel_summary(days=days, user_id=user_id)
    return FunnelSummaryResponse(**summary)


@router.get(
    "/service-status",
    response_model=ServiceStatusResponse,
    summary="Get runtime service status",
    description="Read-only heartbeat status for api, bot, worker, and database",
)
async def get_service_status(
    db: AsyncSession = Depends(get_db),
) -> ServiceStatusResponse:
    """Return heartbeat-based status for external status bots."""
    return ServiceStatusResponse(**await ServiceStatusService(db).get_status())


@router.post(
    "/restart",
    response_model=RestartAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue controlled RememberMe restart",
    description=(
        "Queue an allowlisted restart request for a local RememberMe supervisor. "
        "The API never executes shell commands or talks to Docker directly."
    ),
)
async def request_restart(
    payload: RestartRequestPayload,
) -> RestartAcceptedResponse:
    """Queue a controlled restart request for RememberMe-owned components."""
    if payload.confirm != RESTART_CONFIRMATION:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid restart confirmation",
        )

    try:
        accepted = RestartRequestService().create_request(
            target=payload.target,
            requested_by=payload.requested_by,
            reason=payload.reason,
        )
    except RestartRequestNotSupportedError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=str(exc),
        ) from exc

    return RestartAcceptedResponse(**accepted)


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
    
    Includes counts for users, lists, and reminders with status breakdown.
    
    Args:
        db: Database session
        
    Returns:
        System statistics
    """
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=7)
    
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
    
    lists_total = await get_count(TodoList)
    lists_today = await get_count(TodoList, today_start)
    lists_week = await get_count(TodoList, week_start)

    notes_total = await get_count(Note)
    notes_today = await get_count(Note, today_start)
    notes_week = await get_count(Note, week_start)
    
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
        lists=StatsCount(
            total=lists_total,
            created_today=lists_today,
            created_week=lists_week,
        ),
        notes=StatsCount(
            total=notes_total,
            created_today=notes_today,
            created_week=notes_week,
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
