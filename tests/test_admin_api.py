"""Admin API regression tests."""

from datetime import datetime, timezone

import httpx
import pytest

from src.api.app import create_application
from src.config import settings
from src.db.models import Medication, Reminder, ReminderStatus, RepeatRule, TodoList, User
from src.db.session import get_db
from src.services.driver_service import DriverService


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
    db_session.add_all([todo_list, reminder, medication])
    await db_session.flush()
    driver_service = DriverService(db_session)
    vehicle = await driver_service.create_vehicle(user.id, "API visible vehicle", current_mileage_km=1000)
    await driver_service.add_fuel_entry(user.id, vehicle.id, 1500, 30, 1800, True)

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

    assert users_response.status_code == 200
    assert user_response.status_code == 200
    assert records_response.status_code == 200

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
    assert records_payload["reminders"][0]["text"] == "API visible reminder"
    assert records_payload["medications"][0]["name"] == "API visible medication"
    assert records_payload["driver"]["overview"]["vehicles_count"] == 1
    assert records_payload["driver"]["overview"]["fuel_entries_count"] == 1
    assert records_payload["driver"]["vehicles"][0]["title"] == "API visible vehicle"
