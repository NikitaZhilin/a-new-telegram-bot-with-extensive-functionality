"""Admin API regression tests."""

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from src.api.app import create_application
from src.config import settings
from src.db.models import Medication, Note, Reminder, ReminderStatus, RepeatRule, TodoList, User
from src.db.session import get_db
from src.services.driver_service import DriverService
from src.services.activity_service import ActivityService


@pytest.mark.asyncio
async def test_admin_user_endpoints_serialize_datetimes(db_session):
    """Admin user endpoints should serialize ORM datetime fields as JSON strings."""
    user = User(
        telegram_id=99001,
        username="admin_api_user",
        first_name="Admin",
        timezone="UTC",
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    todo_list = TodoList(user_id=user.id, title="API visible list")
    reminder = Reminder(
        user_id=user.id,
        text="API visible reminder",
        remind_at_utc=datetime(2026, 5, 24, 9, 0, tzinfo=timezone.utc),
        repeat_rule=RepeatRule.NONE,
        status=ReminderStatus.ACTIVE,
    )
    medication = Medication(user_id=user.id, name="API visible medication", importance="normal")
    note = Note(user_id=user.id, title="API visible note", text="Admin-visible note text")
    db_session.add_all([todo_list, note, reminder, medication])
    await db_session.flush()
    driver_service = DriverService(db_session)
    vehicle = await driver_service.create_vehicle(user.id, "API visible vehicle", current_mileage_km=1000)
    await driver_service.add_fuel_entry(user.id, vehicle.id, 1500, 30, 1800, True)
    await driver_service.create_expense(user.id, "API visible expense", 700, vehicle_id=vehicle.id)
    await driver_service.create_document(user.id, "API visible document", vehicle_id=vehicle.id)
    await ActivityService(db_session).record_event(
        user_id=user.id,
        telegram_id=user.telegram_id,
        event_type="callback",
        event_name="driver_menu",
        domain="driver",
    )
    await ActivityService(db_session).record_event(
        user_id=user.id,
        telegram_id=user.telegram_id,
        event_type="callback",
        event_name="driver_fuel_add:{id}",
        domain="driver",
    )

    app = create_application()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    headers = {"X-Admin-Token": settings.ADMIN_TOKEN}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        users_response = await client.get("/admin/users", headers=headers)
        user_response = await client.get(f"/admin/users/{user.id}", headers=headers)
        records_response = await client.get(f"/admin/users/{user.id}/records", headers=headers)
        activity_response = await client.get(f"/admin/activity?current_user_id={user.id}", headers=headers)
        filtered_activity_response = await client.get(
            f"/admin/activity?current_user_id={user.id}&user_id={user.id}",
            headers=headers,
        )
        funnels_response = await client.get("/admin/funnels", headers=headers)
        filtered_funnels_response = await client.get(f"/admin/funnels?user_id={user.id}", headers=headers)
        ui_response = await client.get("/admin/ui")

    assert users_response.status_code == 200
    assert user_response.status_code == 200
    assert records_response.status_code == 200
    assert activity_response.status_code == 200
    assert filtered_activity_response.status_code == 200
    assert funnels_response.status_code == 200
    assert filtered_funnels_response.status_code == 200
    assert ui_response.status_code == 200

    users_payload = users_response.json()
    assert users_payload["total"] == 1
    assert isinstance(users_payload["users"][0]["created_at"], str)
    assert users_payload["users"][0]["created_at"]

    user_payload = user_response.json()
    assert user_payload["id"] == user.id
    assert isinstance(user_payload["created_at"], str)

    records_payload = records_response.json()
    assert records_payload["user"]["id"] == user.id
    assert records_payload["lists"][0]["title"] == "API visible list"
    assert records_payload["notes"][0]["title"] == "API visible note"
    assert records_payload["reminders"][0]["text"] == "API visible reminder"
    assert records_payload["medications"][0]["name"] == "API visible medication"
    assert records_payload["driver"]["overview"]["vehicles_count"] == 1
    assert records_payload["driver"]["overview"]["fuel_entries_count"] == 1
    assert records_payload["driver"]["overview"]["expense_entries_count"] == 1
    assert records_payload["driver"]["overview"]["documents_active_count"] == 1
    assert records_payload["driver"]["vehicles"][0]["title"] == "API visible vehicle"
    assert records_payload["driver"]["expenses"][0]["title"] == "API visible expense"
    assert records_payload["driver"]["documents"][0]["title"] == "API visible document"

    activity_payload = activity_response.json()
    assert activity_payload["events_period"] == 2
    assert activity_payload["top_domains"][0]["domain"] == "driver"
    assert filtered_activity_response.json()["filtered_user_id"] == user.id

    funnels_payload = funnels_response.json()
    assert filtered_funnels_response.json()["filtered_user_id"] == user.id
    driver_funnel = next(item for item in funnels_payload["funnels"] if item["key"] == "driver")
    assert driver_funnel["stages"][0]["key"] == "open"
    assert driver_funnel["stages"][2]["key"] == "fuel_add"
    assert "RememberMe Admin" in ui_response.text


@pytest.mark.asyncio
async def test_admin_stats_week_is_last_seven_days_with_notes(db_session):
    """Admin stats should count the last 7 days, not only today."""
    user = User(telegram_id=99002, username="admin_stats_user", timezone="UTC")
    db_session.add(user)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            TodoList(user_id=user.id, title="Today list", created_at=now),
            TodoList(user_id=user.id, title="Week list", created_at=now - timedelta(days=3)),
            TodoList(user_id=user.id, title="Old list", created_at=now - timedelta(days=10)),
            Note(user_id=user.id, title="Today note", created_at=now),
            Note(user_id=user.id, title="Week note", created_at=now - timedelta(days=3)),
            Note(user_id=user.id, title="Old note", created_at=now - timedelta(days=10)),
        ]
    )
    await db_session.flush()

    app = create_application()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    headers = {"X-Admin-Token": settings.ADMIN_TOKEN}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/admin/stats", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["notes"]["total"] == 3
    assert payload["notes"]["created_today"] == 1
    assert payload["notes"]["created_week"] == 2
    assert payload["lists"]["total"] == 3
    assert payload["lists"]["created_today"] == 1
    assert payload["lists"]["created_week"] == 2
