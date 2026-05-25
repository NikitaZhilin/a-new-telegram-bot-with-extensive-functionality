"""User-scoped API for web clients."""

from datetime import datetime, time, timedelta, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.user_auth import get_current_web_user
from src.config import settings
from src.db.models import (
    DriverDocument,
    DriverExpense,
    DriverVehicle,
    Medication,
    Reminder,
    ReminderStatus,
    TodoList,
    User,
)
from src.db.session import get_db
from src.services.driver_service import DriverService
from src.services.list_service import ListService
from src.services.medication_service import MedicationService
from src.services.reminder_service import ReminderService
from src.services.settings_service import SettingsService
from src.services.subscription_service import SubscriptionService
from src.services.vehicle_presets import list_vehicle_presets
from src.db.models import RepeatRule


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
    access_role: str = "owner"
    items_total: int
    items_done: int
    updated_at: datetime


class ListItemResponse(BaseModel):
    """Todo list item."""

    id: int
    text: str
    is_completed: bool
    position: Optional[int]
    created_at: datetime


class ListDetailResponse(ListSummaryResponse):
    """Todo list with items."""

    items: List[ListItemResponse]


class ListShareLinksResponse(BaseModel):
    """Fresh share/collaboration links for a list owner."""

    copy_link: Optional[str]
    editor_link: Optional[str]
    viewer_link: Optional[str]
    import_command: str
    editor_join_command: str
    viewer_join_command: str


class ListMemberResponse(BaseModel):
    """Shared list member row."""

    member_id: Optional[int]
    user_id: int
    role: str
    display_name: str


class ListCreateRequest(BaseModel):
    """Create a list."""

    title: str = Field(min_length=1, max_length=255)


class ListUpdateRequest(BaseModel):
    """Update a list."""

    title: str = Field(min_length=1, max_length=255)


class ListItemCreateRequest(BaseModel):
    """Create one or many list items."""

    text: str = Field(min_length=1, max_length=4000)


class ListItemUpdateRequest(BaseModel):
    """Update a list item."""

    text: Optional[str] = Field(default=None, min_length=1, max_length=500)
    is_completed: Optional[bool] = None


class ListMemberRoleRequest(BaseModel):
    """Update a shared list member role."""

    role: str = Field(pattern="^(viewer|editor)$")


class ReminderSummaryResponse(BaseModel):
    """Reminder summary."""

    id: int
    title: Optional[str]
    text: str
    source_module: str
    status: str
    remind_at_utc: datetime
    repeat_rule: str


class ReminderCreateRequest(BaseModel):
    """Create a reminder."""

    text: str = Field(min_length=1, max_length=2000)
    title: Optional[str] = Field(default=None, max_length=255)
    remind_at_local: datetime
    repeat_rule: str = "none"


class ReminderUpdateRequest(BaseModel):
    """Update reminder fields."""

    text: Optional[str] = Field(default=None, min_length=1, max_length=2000)
    title: Optional[str] = Field(default=None, max_length=255)
    remind_at_local: Optional[datetime] = None
    repeat_rule: Optional[str] = None


class MedicationSummaryResponse(BaseModel):
    """Medication summary."""

    id: int
    name: str
    dosage: Optional[str]
    instructions: Optional[str]
    importance: str
    is_active: bool
    daily_times_local: List[str] = Field(default_factory=list)
    can_mark_now: bool = False
    mark_reason: str = ""
    has_schedule: bool = False
    next_available_at_utc: Optional[datetime] = None
    marked_at_utc: Optional[datetime] = None
    updated_at: datetime


class MedicationCreateRequest(BaseModel):
    """Create medication."""

    name: str = Field(min_length=1, max_length=255)
    dosage: Optional[str] = Field(default=None, max_length=255)
    instructions: Optional[str] = Field(default=None, max_length=1000)
    importance: str = "normal"
    daily_times_local: List[str] = Field(default_factory=list)


class MedicationUpdateRequest(BaseModel):
    """Update medication."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    dosage: Optional[str] = Field(default=None, max_length=255)
    instructions: Optional[str] = Field(default=None, max_length=1000)
    importance: Optional[str] = None
    daily_times_local: Optional[List[str]] = None


class MutationResponse(BaseModel):
    """Generic mutation response."""

    ok: bool


class DriverVehicleSummaryResponse(BaseModel):
    """Vehicle summary."""

    id: int
    title: str
    preset_slug: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    body_type: Optional[str] = None
    engine_volume_l: Optional[float] = None
    engine_power_hp: Optional[int] = None
    fuel_type: Optional[str] = None
    transmission: Optional[str] = None
    drive_type: Optional[str] = None
    expected_consumption_city_l_per_100: Optional[float] = None
    expected_consumption_highway_l_per_100: Optional[float] = None
    expected_consumption_mixed_l_per_100: Optional[float] = None
    vehicle_specs_note: Optional[str] = None
    current_mileage_km: int
    service_interval_km: int
    service_interval_months: int
    last_service_mileage_km: Optional[int]
    last_service_at_utc: Optional[datetime]
    service_plan: Optional[dict] = None
    updated_at: datetime


class DriverFuelEntryResponse(BaseModel):
    """Vehicle fuel entry."""

    id: int
    vehicle_id: int
    mileage_km: int
    liters: float
    total_cost: float
    price_per_liter: Optional[float]
    is_full_tank: bool
    station: Optional[str]
    note: Optional[str]
    consumption_l_per_100: Optional[float]
    cost_per_km: Optional[float]
    filled_at_utc: datetime


class DriverExpenseResponse(BaseModel):
    """Manual driver expense."""

    id: int
    vehicle_id: Optional[int]
    title: str
    category: str
    amount: float
    note: Optional[str]
    spent_at_utc: datetime
    updated_at: datetime


class DriverDocumentResponse(BaseModel):
    """Driver document or recurring payment tracker."""

    id: int
    vehicle_id: Optional[int]
    title: str
    document_type: str
    identifier: Optional[str]
    expires_at_utc: Optional[datetime]
    remind_before_days: int
    note: Optional[str]
    is_active: bool
    updated_at: datetime


class DriverDashboardResponse(BaseModel):
    """Driver dashboard summary."""

    overview: dict
    vehicles: List[DriverVehicleSummaryResponse]
    expenses: List[DriverExpenseResponse] = Field(default_factory=list)
    documents: List[DriverDocumentResponse] = Field(default_factory=list)


class DriverVehiclePresetResponse(BaseModel):
    """Curated vehicle preset."""

    slug: str
    label: str
    title: str
    make: str
    model: str
    year: Optional[int]
    generation: Optional[str]
    body_type: str
    engine_volume_l: float
    engine_power_hp: Optional[int]
    fuel_type: str
    transmission: str
    drive_type: str
    consumption_city_l_per_100: Optional[float]
    consumption_highway_l_per_100: Optional[float]
    consumption_mixed_l_per_100: Optional[float]
    service_interval_km: int
    service_interval_months: int
    confidence: str
    note: str


class DriverVehicleCreateRequest(BaseModel):
    """Create vehicle."""

    title: str = Field(min_length=1, max_length=255)
    current_mileage_km: int = Field(default=0, ge=0)
    service_interval_km: int = Field(default=10000, gt=0)
    service_interval_months: int = Field(default=12, gt=0)
    preset_slug: Optional[str] = Field(default=None, max_length=120)
    make: Optional[str] = Field(default=None, max_length=120)
    model: Optional[str] = Field(default=None, max_length=120)
    year: Optional[int] = Field(default=None, ge=1886, le=2100)
    body_type: Optional[str] = Field(default=None, max_length=80)
    engine_volume_l: Optional[float] = Field(default=None, gt=0)
    engine_power_hp: Optional[int] = Field(default=None, gt=0)
    fuel_type: Optional[str] = Field(default=None, max_length=40)
    transmission: Optional[str] = Field(default=None, max_length=40)
    drive_type: Optional[str] = Field(default=None, max_length=40)
    expected_consumption_city_l_per_100: Optional[float] = Field(default=None, gt=0)
    expected_consumption_highway_l_per_100: Optional[float] = Field(default=None, gt=0)
    expected_consumption_mixed_l_per_100: Optional[float] = Field(default=None, gt=0)
    vehicle_specs_note: Optional[str] = Field(default=None, max_length=1000)


class DriverVehicleUpdateRequest(BaseModel):
    """Update vehicle fields."""

    title: str = Field(min_length=1, max_length=255)
    current_mileage_km: int = Field(ge=0)
    service_interval_km: int = Field(gt=0)
    service_interval_months: int = Field(gt=0)
    preset_slug: Optional[str] = Field(default=None, max_length=120)
    make: Optional[str] = Field(default=None, max_length=120)
    model: Optional[str] = Field(default=None, max_length=120)
    year: Optional[int] = Field(default=None, ge=1886, le=2100)
    body_type: Optional[str] = Field(default=None, max_length=80)
    engine_volume_l: Optional[float] = Field(default=None, gt=0)
    engine_power_hp: Optional[int] = Field(default=None, gt=0)
    fuel_type: Optional[str] = Field(default=None, max_length=40)
    transmission: Optional[str] = Field(default=None, max_length=40)
    drive_type: Optional[str] = Field(default=None, max_length=40)
    expected_consumption_city_l_per_100: Optional[float] = Field(default=None, gt=0)
    expected_consumption_highway_l_per_100: Optional[float] = Field(default=None, gt=0)
    expected_consumption_mixed_l_per_100: Optional[float] = Field(default=None, gt=0)
    vehicle_specs_note: Optional[str] = Field(default=None, max_length=1000)


class DriverFuelCreateRequest(BaseModel):
    """Create fuel entry."""

    mileage_km: int = Field(ge=0)
    liters: float = Field(gt=0)
    total_cost: float = Field(gt=0)
    is_full_tank: bool = True
    station: Optional[str] = Field(default=None, max_length=255)
    note: Optional[str] = Field(default=None, max_length=1000)


class DriverFuelUpdateRequest(DriverFuelCreateRequest):
    """Update fuel entry."""


class DriverServiceDoneRequest(BaseModel):
    """Mark vehicle service as completed."""

    service_mileage_km: int = Field(ge=0)


class DriverExpenseCreateRequest(BaseModel):
    """Create manual expense."""

    title: str = Field(min_length=1, max_length=255)
    category: str = Field(default="other", max_length=80)
    amount: float = Field(gt=0)
    vehicle_id: Optional[int] = None
    spent_at_local: Optional[datetime] = None
    note: Optional[str] = Field(default=None, max_length=1000)


class DriverExpenseUpdateRequest(DriverExpenseCreateRequest):
    """Update manual expense."""


class DriverDocumentCreateRequest(BaseModel):
    """Create driver document."""

    title: str = Field(min_length=1, max_length=255)
    document_type: str = Field(default="other", max_length=80)
    vehicle_id: Optional[int] = None
    identifier: Optional[str] = Field(default=None, max_length=255)
    expires_at_local: Optional[datetime] = None
    remind_before_days: int = Field(default=14, ge=0)
    note: Optional[str] = Field(default=None, max_length=1000)
    is_active: bool = True


class DriverDocumentUpdateRequest(DriverDocumentCreateRequest):
    """Update driver document."""


def _repeat_rule(value: str) -> RepeatRule:
    """Parse repeat rule from user API input."""
    try:
        return RepeatRule(value)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid repeat_rule",
        ) from None


def _local_datetime_to_utc(value: datetime, user_timezone: str) -> datetime:
    """Convert browser-local datetime to UTC."""
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc)
    return value.replace(tzinfo=ZoneInfo(user_timezone)).astimezone(timezone.utc)


def _local_time_to_next_utc(value: str, user_timezone: str) -> datetime:
    """Convert HH:MM to next local occurrence in UTC."""
    try:
        parsed = time.fromisoformat(value.strip())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Daily time must be HH:MM",
        ) from None

    tz = ZoneInfo(user_timezone)
    now_local = datetime.now(tz)
    local_dt = datetime.combine(now_local.date(), parsed, tzinfo=tz)
    if local_dt <= now_local:
        local_dt = local_dt + timedelta(days=1)
    return local_dt.astimezone(timezone.utc)


def _item_response(item) -> ListItemResponse:
    """Serialize list item."""
    return ListItemResponse(
        id=item.id,
        text=item.text,
        is_completed=item.is_completed,
        position=item.position,
        created_at=item.created_at,
    )


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


async def _list_response(list_obj: TodoList, user_id: int, service: ListService) -> ListDetailResponse:
    """Serialize list with items and access role."""
    role = await service.get_access_role(list_obj.id, user_id) or "viewer"
    return ListDetailResponse(
        id=list_obj.id,
        title=list_obj.title,
        source_module=list_obj.source_module,
        access_role=role,
        items_total=len(list_obj.items),
        items_done=sum(1 for item in list_obj.items if item.is_completed),
        updated_at=list_obj.updated_at,
        items=[_item_response(item) for item in list_obj.items],
    )


async def _fresh_list(db: AsyncSession, list_id: int) -> Optional[TodoList]:
    """Load a list with fresh item relationship state."""
    result = await db.execute(
        select(TodoList)
        .options(selectinload(TodoList.items))
        .where(TodoList.id == list_id)
        .execution_options(populate_existing=True)
    )
    return result.scalars().unique().one_or_none()


def _reminder_response(reminder: Reminder) -> ReminderSummaryResponse:
    """Serialize Reminder ORM object."""
    return ReminderSummaryResponse(
        id=reminder.id,
        title=reminder.title,
        text=reminder.text,
        source_module=reminder.source_module,
        status=reminder.status.value if hasattr(reminder.status, "value") else reminder.status,
        remind_at_utc=reminder.remind_at_utc,
        repeat_rule=reminder.repeat_rule.value if hasattr(reminder.repeat_rule, "value") else reminder.repeat_rule,
    )


def _service_plan_payload(plan: Optional[dict]) -> Optional[dict]:
    """Strip ORM objects from driver service plan payload."""
    if not plan:
        return None
    return {
        "next_mileage": plan.get("next_mileage"),
        "remaining_km": plan.get("remaining_km"),
        "mileage_status": plan.get("mileage_status"),
        "next_date": plan.get("next_date"),
        "days_left": plan.get("days_left"),
        "date_status": plan.get("date_status"),
    }


async def _vehicle_response(
    vehicle: DriverVehicle,
    user_id: int,
    service: DriverService,
) -> DriverVehicleSummaryResponse:
    """Serialize driver vehicle with service plan."""
    return DriverVehicleSummaryResponse(
        id=vehicle.id,
        title=vehicle.title,
        preset_slug=vehicle.preset_slug,
        make=vehicle.make,
        model=vehicle.model,
        year=vehicle.year,
        body_type=vehicle.body_type,
        engine_volume_l=vehicle.engine_volume_l,
        engine_power_hp=vehicle.engine_power_hp,
        fuel_type=vehicle.fuel_type,
        transmission=vehicle.transmission,
        drive_type=vehicle.drive_type,
        expected_consumption_city_l_per_100=vehicle.expected_consumption_city_l_per_100,
        expected_consumption_highway_l_per_100=vehicle.expected_consumption_highway_l_per_100,
        expected_consumption_mixed_l_per_100=vehicle.expected_consumption_mixed_l_per_100,
        vehicle_specs_note=vehicle.vehicle_specs_note,
        current_mileage_km=vehicle.current_mileage_km,
        service_interval_km=vehicle.service_interval_km,
        service_interval_months=vehicle.service_interval_months,
        last_service_mileage_km=vehicle.last_service_mileage_km,
        last_service_at_utc=vehicle.last_service_at_utc,
        service_plan=_service_plan_payload(await service.get_service_plan(vehicle.id, user_id)),
        updated_at=vehicle.updated_at,
    )


def _fuel_entry_response(entry) -> DriverFuelEntryResponse:
    """Serialize driver fuel entry."""
    return DriverFuelEntryResponse(
        id=entry.id,
        vehicle_id=entry.vehicle_id,
        mileage_km=entry.mileage_km,
        liters=entry.liters,
        total_cost=entry.total_cost,
        price_per_liter=entry.price_per_liter,
        is_full_tank=entry.is_full_tank,
        station=entry.station,
        note=entry.note,
        consumption_l_per_100=entry.consumption_l_per_100,
        cost_per_km=entry.cost_per_km,
        filled_at_utc=entry.filled_at_utc,
    )


def _expense_response(expense: DriverExpense) -> DriverExpenseResponse:
    """Serialize manual driver expense."""
    return DriverExpenseResponse(
        id=expense.id,
        vehicle_id=expense.vehicle_id,
        title=expense.title,
        category=expense.category,
        amount=expense.amount,
        note=expense.note,
        spent_at_utc=expense.spent_at_utc,
        updated_at=expense.updated_at,
    )


def _document_response(document: DriverDocument) -> DriverDocumentResponse:
    """Serialize driver document."""
    return DriverDocumentResponse(
        id=document.id,
        vehicle_id=document.vehicle_id,
        title=document.title,
        document_type=document.document_type,
        identifier=document.identifier,
        expires_at_utc=document.expires_at_utc,
        remind_before_days=document.remind_before_days,
        note=document.note,
        is_active=document.is_active,
        updated_at=document.updated_at,
    )


async def _medication_response(
    service: MedicationService,
    medication: Medication,
    user: User,
) -> MedicationSummaryResponse:
    """Serialize a medication with web action state."""
    schedule = await service._get_daily_schedule_times(  # noqa: SLF001 - read-only web presentation helper
        medication.id,
        user.id,
        user.timezone,
    )
    action_state = await service.get_intake_action_state(
        medication.id,
        user.id,
        user.timezone,
    )
    return MedicationSummaryResponse(
        id=medication.id,
        name=medication.name,
        dosage=medication.dosage,
        instructions=medication.instructions,
        importance=medication.importance,
        is_active=medication.is_active,
        daily_times_local=[value.strftime("%H:%M") for value in schedule],
        can_mark_now=action_state.can_mark,
        mark_reason=action_state.reason,
        has_schedule=action_state.has_schedule,
        next_available_at_utc=action_state.next_available_at_utc,
        marked_at_utc=action_state.marked_at_utc,
        updated_at=medication.updated_at,
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
    """Return generic lists visible to current user."""
    list_service = ListService(db)
    lists, _ = await list_service.get_lists_list(
        current_user.id,
        page=0,
        page_size=limit,
        source_module="general",
    )
    return [
        ListSummaryResponse(
            id=item.id,
            title=item.title,
            source_module=item.source_module,
            access_role=getattr(item, "_access_role", None)
            or await list_service.get_access_role(item.id, current_user.id)
            or "viewer",
            items_total=len(item.items),
            items_done=sum(1 for list_item in item.items if list_item.is_completed),
            updated_at=item.updated_at,
        )
        for item in lists
    ]


@router.post("/me/lists", response_model=ListDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_my_list(
    payload: ListCreateRequest,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> ListDetailResponse:
    """Create a generic user list."""
    service = ListService(db)
    list_obj = await service.create_list(current_user.id, payload.title.strip(), source_module="general")
    list_obj = await _fresh_list(db, list_obj.id)
    await db.commit()
    if not list_obj:
        raise HTTPException(status_code=500, detail="List was not created")
    return await _list_response(list_obj, current_user.id, service)


@router.get("/me/lists/{list_id}", response_model=ListDetailResponse)
async def get_my_list(
    list_id: int,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> ListDetailResponse:
    """Return one generic list with items."""
    service = ListService(db)
    list_obj = await service.get_list(list_id, current_user.id)
    if not list_obj or list_obj.source_module != "general":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="List not found")
    return await _list_response(list_obj, current_user.id, service)


@router.patch("/me/lists/{list_id}", response_model=ListDetailResponse)
async def update_my_list(
    list_id: int,
    payload: ListUpdateRequest,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> ListDetailResponse:
    """Rename a user-owned list."""
    service = ListService(db)
    existing = await service.get_list(list_id, current_user.id)
    if not existing or existing.source_module != "general":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="List not found")
    list_obj = await service.update_list_title(list_id, current_user.id, payload.title.strip())
    if not list_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="List not found")
    list_obj = await _fresh_list(db, list_id)
    await db.commit()
    return await _list_response(list_obj, current_user.id, service)  # type: ignore[arg-type]


@router.delete("/me/lists/{list_id}", response_model=MutationResponse)
async def delete_my_list(
    list_id: int,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> MutationResponse:
    """Delete a user-owned generic list."""
    service = ListService(db)
    list_obj = await service.get_list(list_id, current_user.id)
    if not list_obj or list_obj.source_module != "general":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="List not found")
    ok = await service.delete_list(list_id, current_user.id)
    await db.commit()
    return MutationResponse(ok=ok)


@router.post("/me/lists/{list_id}/items", response_model=ListDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_my_list_items(
    list_id: int,
    payload: ListItemCreateRequest,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> ListDetailResponse:
    """Add one or many items to a list."""
    service = ListService(db)
    list_obj = await service.get_list(list_id, current_user.id)
    if not list_obj or list_obj.source_module != "general":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="List not found")
    lines = [line.strip() for line in payload.text.splitlines() if line.strip()]
    if len(lines) > 1:
        await service.add_items_bulk(list_id, current_user.id, lines)
    else:
        await service.add_item(list_id, current_user.id, payload.text.strip())
    list_obj = await _fresh_list(db, list_id)
    await db.commit()
    return await _list_response(list_obj, current_user.id, service)  # type: ignore[arg-type]


@router.patch("/me/lists/items/{item_id}", response_model=ListDetailResponse)
async def update_my_list_item(
    item_id: int,
    payload: ListItemUpdateRequest,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> ListDetailResponse:
    """Update a list item text or completion flag."""
    service = ListService(db)
    item = await service.get_item_by_id(item_id, current_user.id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    list_obj = await service.get_list(item.list_id, current_user.id)
    if not list_obj or list_obj.source_module != "general":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    if payload.text is not None:
        updated = await service.update_item_text_by_id(item_id, current_user.id, payload.text.strip())
        if not updated:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No edit access to item")
    if payload.is_completed is not None and item.is_completed != payload.is_completed:
        updated = await service.toggle_item_by_id(item_id, current_user.id)
        if not updated:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No edit access to item")
    list_obj = await _fresh_list(db, list_obj.id)
    await db.commit()
    return await _list_response(list_obj, current_user.id, service)  # type: ignore[arg-type]


@router.delete("/me/lists/items/{item_id}", response_model=ListDetailResponse)
async def delete_my_list_item(
    item_id: int,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> ListDetailResponse:
    """Delete a list item."""
    service = ListService(db)
    item = await service.get_item_by_id(item_id, current_user.id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    list_id = item.list_id
    list_obj = await service.get_list(list_id, current_user.id)
    if not list_obj or list_obj.source_module != "general":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    ok = await service.delete_item_by_id(item_id, current_user.id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No edit access to item")
    list_obj = await _fresh_list(db, list_id)
    await db.commit()
    return await _list_response(list_obj, current_user.id, service)  # type: ignore[arg-type]


@router.post("/me/lists/{list_id}/share", response_model=ListShareLinksResponse)
async def create_my_list_share_links(
    list_id: int,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> ListShareLinksResponse:
    """Create fresh copy/editor/viewer tokens for a list owner."""
    service = ListService(db)
    list_obj = await service.get_list(list_id, current_user.id)
    if not list_obj or list_obj.source_module != "general":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="List not found")

    copy_token = await service.create_share_token(list_id, current_user.id)
    editor_token = await service.create_collaboration_token(list_id, current_user.id, role="editor")
    viewer_token = await service.create_collaboration_token(list_id, current_user.id, role="viewer")
    if not copy_token or not editor_token or not viewer_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only list owner can share this list")

    await db.commit()
    copy_command = f"/import_list {copy_token.token}"
    editor_command = f"/join_list {editor_token.token}"
    viewer_command = f"/join_list {viewer_token.token}"
    if settings.BOT_USERNAME:
        bot_base = f"https://t.me/{settings.BOT_USERNAME}"
        copy_link = f"{bot_base}?start=import_list_{copy_token.token}"
        editor_link = f"{bot_base}?start=join_list_{editor_token.token}"
        viewer_link = f"{bot_base}?start=join_list_{viewer_token.token}"
    else:
        copy_link = editor_link = viewer_link = None

    return ListShareLinksResponse(
        copy_link=copy_link,
        editor_link=editor_link,
        viewer_link=viewer_link,
        import_command=copy_command,
        editor_join_command=editor_command,
        viewer_join_command=viewer_command,
    )


@router.get("/me/lists/{list_id}/members", response_model=List[ListMemberResponse])
async def get_my_list_members(
    list_id: int,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> List[ListMemberResponse]:
    """Return list members for owner management."""
    service = ListService(db)
    list_obj = await service.get_list(list_id, current_user.id)
    if not list_obj or list_obj.source_module != "general":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="List not found")
    members = await service.get_list_members(list_id, current_user.id)
    if members is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only list owner can view members")
    return [ListMemberResponse(**item) for item in members]


@router.patch("/me/lists/{list_id}/members/{member_id}", response_model=ListMemberResponse)
async def update_my_list_member_role(
    list_id: int,
    member_id: int,
    payload: ListMemberRoleRequest,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> ListMemberResponse:
    """Change a shared list member role."""
    service = ListService(db)
    member = await service.update_member_role(list_id, current_user.id, member_id, payload.role)
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    await db.commit()
    members = await service.get_list_members(list_id, current_user.id)
    row = next((item for item in members or [] if item["member_id"] == member_id), None)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    return ListMemberResponse(**row)


@router.delete("/me/lists/{list_id}/members/{member_id}", response_model=MutationResponse)
async def remove_my_list_member(
    list_id: int,
    member_id: int,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> MutationResponse:
    """Revoke a shared list member access."""
    service = ListService(db)
    ok = await service.remove_member(list_id, current_user.id, member_id)
    await db.commit()
    return MutationResponse(ok=ok)


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


@router.post("/me/reminders", response_model=ReminderSummaryResponse, status_code=status.HTTP_201_CREATED)
async def create_my_reminder(
    payload: ReminderCreateRequest,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> ReminderSummaryResponse:
    """Create a generic reminder from web UI."""
    service = ReminderService(db)
    reminder = await service.create_reminder(
        user_id=current_user.id,
        text=payload.text.strip(),
        title=payload.title.strip() if payload.title else None,
        remind_at_utc=_local_datetime_to_utc(payload.remind_at_local, current_user.timezone),
        repeat_rule=_repeat_rule(payload.repeat_rule),
        source_module="general",
    )
    if not reminder:
        raise HTTPException(status_code=400, detail="Reminder was not created")
    await db.commit()
    await db.refresh(reminder)
    return _reminder_response(reminder)


@router.patch("/me/reminders/{reminder_id}", response_model=ReminderSummaryResponse)
async def update_my_reminder(
    reminder_id: int,
    payload: ReminderUpdateRequest,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> ReminderSummaryResponse:
    """Update a generic reminder from web UI."""
    service = ReminderService(db)
    reminder = await service.get_reminder(reminder_id, current_user.id)
    if not reminder or reminder.source_module != "general":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found")

    if payload.text is not None:
        reminder = await service.update_reminder_text(reminder_id, current_user.id, payload.text.strip())
    if payload.remind_at_local is not None:
        reminder = await service.update_reminder_time(
            reminder_id,
            current_user.id,
            _local_datetime_to_utc(payload.remind_at_local, current_user.timezone),
        )
    if payload.repeat_rule is not None:
        reminder = await service.update_reminder_repeat(reminder_id, current_user.id, _repeat_rule(payload.repeat_rule))
    if payload.title is not None and reminder is not None:
        reminder.title = payload.title.strip() or None

    if not reminder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found")
    await db.commit()
    await db.refresh(reminder)
    return _reminder_response(reminder)


@router.post("/me/reminders/{reminder_id}/done", response_model=ReminderSummaryResponse)
async def mark_my_reminder_done(
    reminder_id: int,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> ReminderSummaryResponse:
    """Mark reminder as done."""
    service = ReminderService(db)
    existing = await service.get_reminder(reminder_id, current_user.id)
    if not existing or existing.source_module != "general":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found")
    reminder = await service.mark_reminder_done(reminder_id, current_user.id)
    if not reminder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found")
    await db.commit()
    await db.refresh(reminder)
    return _reminder_response(reminder)


@router.post("/me/reminders/{reminder_id}/cancel", response_model=ReminderSummaryResponse)
async def cancel_my_reminder(
    reminder_id: int,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> ReminderSummaryResponse:
    """Mark reminder as canceled."""
    service = ReminderService(db)
    existing = await service.get_reminder(reminder_id, current_user.id)
    if not existing or existing.source_module != "general":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found")
    reminder = await service.mark_reminder_canceled(reminder_id, current_user.id)
    if not reminder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found")
    await db.commit()
    await db.refresh(reminder)
    return _reminder_response(reminder)


@router.delete("/me/reminders/{reminder_id}", response_model=MutationResponse)
async def delete_my_reminder(
    reminder_id: int,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> MutationResponse:
    """Delete a generic reminder."""
    service = ReminderService(db)
    reminder = await service.get_reminder(reminder_id, current_user.id)
    if not reminder or reminder.source_module != "general":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found")
    ok = await service.delete_reminder(reminder_id, current_user.id)
    await db.commit()
    return MutationResponse(ok=ok)


@router.get("/me/medications", response_model=List[MedicationSummaryResponse])
async def get_my_medications(
    active_only: bool = Query(True),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> List[MedicationSummaryResponse]:
    """Return current user's medications."""
    medication_service = MedicationService(db)
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
    return [await _medication_response(medication_service, item, current_user) for item in medications]


@router.post("/me/medications", response_model=MedicationSummaryResponse, status_code=status.HTTP_201_CREATED)
async def create_my_medication(
    payload: MedicationCreateRequest,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> MedicationSummaryResponse:
    """Create a medication and optional daily schedule."""
    service = MedicationService(db)
    medication = await service.create_medication(
        user_id=current_user.id,
        name=payload.name,
        dosage=payload.dosage,
        instructions=payload.instructions,
        importance=payload.importance,
    )
    times = [_local_time_to_next_utc(value, current_user.timezone) for value in payload.daily_times_local if value.strip()]
    if times:
        await service.replace_daily_reminders(medication.id, current_user.id, times)
    await db.commit()
    await db.refresh(medication)
    return await _medication_response(service, medication, current_user)


@router.patch("/me/medications/{medication_id}", response_model=MedicationSummaryResponse)
async def update_my_medication(
    medication_id: int,
    payload: MedicationUpdateRequest,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> MedicationSummaryResponse:
    """Update medication details and schedule."""
    service = MedicationService(db)
    medication = await service.update_medication(
        medication_id=medication_id,
        user_id=current_user.id,
        name=payload.name,
        dosage=payload.dosage,
        instructions=payload.instructions,
        importance=payload.importance,
    )
    if not medication:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Medication not found")
    if payload.daily_times_local is not None:
        times = [_local_time_to_next_utc(value, current_user.timezone) for value in payload.daily_times_local if value.strip()]
        await service.replace_daily_reminders(medication.id, current_user.id, times)
    await db.commit()
    await db.refresh(medication)
    return await _medication_response(service, medication, current_user)


@router.post("/me/medications/{medication_id}/taken", response_model=MutationResponse)
async def mark_my_medication_taken(
    medication_id: int,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> MutationResponse:
    """Mark current medication slot as taken."""
    service = MedicationService(db)
    intake, _ = await service.mark_taken_for_current_slot(medication_id, current_user.id, current_user.timezone)
    await db.commit()
    return MutationResponse(ok=intake is not None)


@router.post("/me/medications/{medication_id}/skipped", response_model=MutationResponse)
async def mark_my_medication_skipped(
    medication_id: int,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> MutationResponse:
    """Mark current medication slot as skipped."""
    service = MedicationService(db)
    intake, _ = await service.mark_skipped_for_current_slot(medication_id, current_user.id, current_user.timezone)
    await db.commit()
    return MutationResponse(ok=intake is not None)


@router.delete("/me/medications/{medication_id}", response_model=MutationResponse)
async def archive_my_medication(
    medication_id: int,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> MutationResponse:
    """Archive a medication."""
    service = MedicationService(db)
    ok = await service.archive_medication(medication_id, current_user.id)
    await db.commit()
    return MutationResponse(ok=ok)


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
    expenses = await driver_service.get_expenses(current_user.id, limit=20)
    documents = await driver_service.get_documents(current_user.id, active_only=False, limit=50)
    return DriverDashboardResponse(
        overview=overview,
        vehicles=[await _vehicle_response(item, current_user.id, driver_service) for item in vehicles],
        expenses=[_expense_response(item) for item in expenses],
        documents=[_document_response(item) for item in documents],
    )


@router.get("/me/driver/vehicle-presets", response_model=List[DriverVehiclePresetResponse])
async def get_my_driver_vehicle_presets(
    current_user: User = Depends(get_current_web_user),
) -> List[DriverVehiclePresetResponse]:
    """Return curated vehicle presets for quick vehicle creation."""
    return [DriverVehiclePresetResponse(**preset.as_dict()) for preset in list_vehicle_presets()]


@router.post("/me/driver/vehicles", response_model=DriverVehicleSummaryResponse, status_code=status.HTTP_201_CREATED)
async def create_my_driver_vehicle(
    payload: DriverVehicleCreateRequest,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> DriverVehicleSummaryResponse:
    """Create a vehicle profile."""
    service = DriverService(db)
    try:
        vehicle = await service.create_vehicle(
            user_id=current_user.id,
            title=payload.title.strip(),
            current_mileage_km=payload.current_mileage_km,
            service_interval_km=payload.service_interval_km,
            service_interval_months=payload.service_interval_months,
            preset_slug=payload.preset_slug,
            make=payload.make,
            model=payload.model,
            year=payload.year,
            body_type=payload.body_type,
            engine_volume_l=payload.engine_volume_l,
            engine_power_hp=payload.engine_power_hp,
            fuel_type=payload.fuel_type,
            transmission=payload.transmission,
            drive_type=payload.drive_type,
            expected_consumption_city_l_per_100=payload.expected_consumption_city_l_per_100,
            expected_consumption_highway_l_per_100=payload.expected_consumption_highway_l_per_100,
            expected_consumption_mixed_l_per_100=payload.expected_consumption_mixed_l_per_100,
            vehicle_specs_note=payload.vehicle_specs_note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    await db.commit()
    await db.refresh(vehicle)
    return await _vehicle_response(vehicle, current_user.id, service)


@router.patch("/me/driver/vehicles/{vehicle_id}", response_model=DriverVehicleSummaryResponse)
async def update_my_driver_vehicle(
    vehicle_id: int,
    payload: DriverVehicleUpdateRequest,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> DriverVehicleSummaryResponse:
    """Update a vehicle profile."""
    service = DriverService(db)
    spec_fields = {
        "preset_slug",
        "make",
        "model",
        "year",
        "body_type",
        "engine_volume_l",
        "engine_power_hp",
        "fuel_type",
        "transmission",
        "drive_type",
        "expected_consumption_city_l_per_100",
        "expected_consumption_highway_l_per_100",
        "expected_consumption_mixed_l_per_100",
        "vehicle_specs_note",
    }
    try:
        vehicle = await service.update_vehicle(
            vehicle_id=vehicle_id,
            user_id=current_user.id,
            title=payload.title.strip(),
            current_mileage_km=payload.current_mileage_km,
            service_interval_km=payload.service_interval_km,
            service_interval_months=payload.service_interval_months,
            update_specs=bool(payload.model_fields_set & spec_fields),
            preset_slug=payload.preset_slug,
            make=payload.make,
            model=payload.model,
            year=payload.year,
            body_type=payload.body_type,
            engine_volume_l=payload.engine_volume_l,
            engine_power_hp=payload.engine_power_hp,
            fuel_type=payload.fuel_type,
            transmission=payload.transmission,
            drive_type=payload.drive_type,
            expected_consumption_city_l_per_100=payload.expected_consumption_city_l_per_100,
            expected_consumption_highway_l_per_100=payload.expected_consumption_highway_l_per_100,
            expected_consumption_mixed_l_per_100=payload.expected_consumption_mixed_l_per_100,
            vehicle_specs_note=payload.vehicle_specs_note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    await db.commit()
    await db.refresh(vehicle)
    return await _vehicle_response(vehicle, current_user.id, service)


@router.post("/me/driver/vehicles/{vehicle_id}/service-done", response_model=DriverVehicleSummaryResponse)
async def mark_my_driver_service_done(
    vehicle_id: int,
    payload: DriverServiceDoneRequest,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> DriverVehicleSummaryResponse:
    """Mark regular service as completed for a vehicle."""
    service = DriverService(db)
    try:
        vehicle = await service.mark_service_done(
            vehicle_id=vehicle_id,
            user_id=current_user.id,
            service_mileage_km=payload.service_mileage_km,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    await db.commit()
    await db.refresh(vehicle)
    return await _vehicle_response(vehicle, current_user.id, service)


@router.delete("/me/driver/vehicles/{vehicle_id}", response_model=MutationResponse)
async def delete_my_driver_vehicle(
    vehicle_id: int,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> MutationResponse:
    """Delete a vehicle profile."""
    service = DriverService(db)
    ok = await service.delete_vehicle(vehicle_id, current_user.id)
    await db.commit()
    return MutationResponse(ok=ok)


@router.get("/me/driver/vehicles/{vehicle_id}/fuel", response_model=List[DriverFuelEntryResponse])
async def get_my_driver_fuel_entries(
    vehicle_id: int,
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> List[DriverFuelEntryResponse]:
    """Return recent fuel entries for one vehicle."""
    service = DriverService(db)
    vehicle = await service.get_vehicle(vehicle_id, current_user.id)
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    entries = await service.get_fuel_entries(current_user.id, vehicle_id=vehicle_id, limit=limit)
    return [_fuel_entry_response(item) for item in entries]


@router.post("/me/driver/vehicles/{vehicle_id}/fuel", response_model=DriverFuelEntryResponse, status_code=status.HTTP_201_CREATED)
async def create_my_driver_fuel_entry(
    vehicle_id: int,
    payload: DriverFuelCreateRequest,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> DriverFuelEntryResponse:
    """Create a fuel journal entry."""
    service = DriverService(db)
    try:
        entry = await service.add_fuel_entry(
            user_id=current_user.id,
            vehicle_id=vehicle_id,
            mileage_km=payload.mileage_km,
            liters=payload.liters,
            total_cost=payload.total_cost,
            is_full_tank=payload.is_full_tank,
            station=payload.station,
            note=payload.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    await db.commit()
    await db.refresh(entry)
    return _fuel_entry_response(entry)


@router.patch("/me/driver/fuel/{entry_id}", response_model=DriverFuelEntryResponse)
async def update_my_driver_fuel_entry(
    entry_id: int,
    payload: DriverFuelUpdateRequest,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> DriverFuelEntryResponse:
    """Update a fuel journal entry."""
    service = DriverService(db)
    try:
        entry = await service.update_fuel_entry(
            entry_id=entry_id,
            user_id=current_user.id,
            mileage_km=payload.mileage_km,
            liters=payload.liters,
            total_cost=payload.total_cost,
            is_full_tank=payload.is_full_tank,
            station=payload.station,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fuel entry not found")
    entry.note = payload.note
    await db.commit()
    await db.refresh(entry)
    return _fuel_entry_response(entry)


@router.delete("/me/driver/fuel/{entry_id}", response_model=MutationResponse)
async def delete_my_driver_fuel_entry(
    entry_id: int,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> MutationResponse:
    """Delete a fuel entry."""
    service = DriverService(db)
    ok = await service.delete_fuel_entry(entry_id, current_user.id)
    await db.commit()
    return MutationResponse(ok=ok)


@router.get("/me/driver/expenses", response_model=List[DriverExpenseResponse])
async def get_my_driver_expenses(
    vehicle_id: Optional[int] = Query(default=None, ge=1),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> List[DriverExpenseResponse]:
    """Return manual driver expenses."""
    service = DriverService(db)
    if vehicle_id is not None and not await service.get_vehicle(vehicle_id, current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    entries = await service.get_expenses(current_user.id, vehicle_id=vehicle_id, limit=limit)
    return [_expense_response(item) for item in entries]


@router.post("/me/driver/expenses", response_model=DriverExpenseResponse, status_code=status.HTTP_201_CREATED)
async def create_my_driver_expense(
    payload: DriverExpenseCreateRequest,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> DriverExpenseResponse:
    """Create a manual driver expense."""
    service = DriverService(db)
    try:
        entry = await service.create_expense(
            user_id=current_user.id,
            vehicle_id=payload.vehicle_id,
            title=payload.title,
            category=payload.category,
            amount=payload.amount,
            spent_at_utc=_local_datetime_to_utc(payload.spent_at_local, current_user.timezone)
            if payload.spent_at_local
            else None,
            note=payload.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    await db.commit()
    await db.refresh(entry)
    return _expense_response(entry)


@router.patch("/me/driver/expenses/{expense_id}", response_model=DriverExpenseResponse)
async def update_my_driver_expense(
    expense_id: int,
    payload: DriverExpenseUpdateRequest,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> DriverExpenseResponse:
    """Update a manual driver expense."""
    service = DriverService(db)
    try:
        entry = await service.update_expense(
            expense_id=expense_id,
            user_id=current_user.id,
            vehicle_id=payload.vehicle_id,
            title=payload.title,
            category=payload.category,
            amount=payload.amount,
            spent_at_utc=_local_datetime_to_utc(payload.spent_at_local, current_user.timezone)
            if payload.spent_at_local
            else None,
            note=payload.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found")
    await db.commit()
    await db.refresh(entry)
    return _expense_response(entry)


@router.delete("/me/driver/expenses/{expense_id}", response_model=MutationResponse)
async def delete_my_driver_expense(
    expense_id: int,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> MutationResponse:
    """Delete a manual driver expense."""
    ok = await DriverService(db).delete_expense(expense_id, current_user.id)
    await db.commit()
    return MutationResponse(ok=ok)


@router.get("/me/driver/documents", response_model=List[DriverDocumentResponse])
async def get_my_driver_documents(
    vehicle_id: Optional[int] = Query(default=None, ge=1),
    active_only: bool = Query(False),
    limit: int = Query(100, ge=1, le=200),
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> List[DriverDocumentResponse]:
    """Return driver documents."""
    service = DriverService(db)
    if vehicle_id is not None and not await service.get_vehicle(vehicle_id, current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    documents = await service.get_documents(
        current_user.id,
        vehicle_id=vehicle_id,
        active_only=active_only,
        limit=limit,
    )
    return [_document_response(item) for item in documents]


@router.post("/me/driver/documents", response_model=DriverDocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_my_driver_document(
    payload: DriverDocumentCreateRequest,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> DriverDocumentResponse:
    """Create a driver document."""
    service = DriverService(db)
    try:
        document = await service.create_document(
            user_id=current_user.id,
            vehicle_id=payload.vehicle_id,
            title=payload.title,
            document_type=payload.document_type,
            identifier=payload.identifier,
            expires_at_utc=_local_datetime_to_utc(payload.expires_at_local, current_user.timezone)
            if payload.expires_at_local
            else None,
            remind_before_days=payload.remind_before_days,
            note=payload.note,
            is_active=payload.is_active,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    await db.commit()
    await db.refresh(document)
    return _document_response(document)


@router.patch("/me/driver/documents/{document_id}", response_model=DriverDocumentResponse)
async def update_my_driver_document(
    document_id: int,
    payload: DriverDocumentUpdateRequest,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> DriverDocumentResponse:
    """Update a driver document."""
    service = DriverService(db)
    try:
        document = await service.update_document(
            document_id=document_id,
            user_id=current_user.id,
            vehicle_id=payload.vehicle_id,
            title=payload.title,
            document_type=payload.document_type,
            identifier=payload.identifier,
            expires_at_utc=_local_datetime_to_utc(payload.expires_at_local, current_user.timezone)
            if payload.expires_at_local
            else None,
            remind_before_days=payload.remind_before_days,
            note=payload.note,
            is_active=payload.is_active,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    await db.commit()
    await db.refresh(document)
    return _document_response(document)


@router.delete("/me/driver/documents/{document_id}", response_model=MutationResponse)
async def delete_my_driver_document(
    document_id: int,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> MutationResponse:
    """Delete a driver document."""
    ok = await DriverService(db).delete_document(document_id, current_user.id)
    await db.commit()
    return MutationResponse(ok=ok)
