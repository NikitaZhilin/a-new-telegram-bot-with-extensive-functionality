"""User-scoped API tests."""

import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
import pytest

from src.api.app import create_application
from src.config import settings
from src.db.models import Medication, Reminder, ReminderStatus, RepeatRule, User
from src.db.session import get_db
from src.services.driver_service import DriverService
from src.services.list_service import ListService
from src.services.reminder_service import ReminderService


def _telegram_init_data(user_payload: dict) -> str:
    """Build signed Telegram WebApp initData for tests."""
    params = {
        "auth_date": str(int(time.time())),
        "query_id": "test-query",
        "user": json.dumps(user_payload, separators=(",", ":")),
    }
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", settings.BOT_TOKEN.encode("utf-8"), hashlib.sha256).digest()
    params["hash"] = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    return urlencode(params)


@pytest.mark.asyncio
async def test_user_api_returns_isolated_current_user_data(db_session):
    """User API should be scoped by validated Telegram initData."""
    user = User(telegram_id=93001, username="web_user", first_name="Web", timezone="UTC")
    other = User(telegram_id=93002, username="other", first_name="Other", timezone="UTC")
    db_session.add_all([user, other])
    await db_session.flush()

    list_service = ListService(db_session)
    own_list = await list_service.create_list(user.id, "Web list")
    await list_service.add_item(own_list.id, user.id, "First")
    await list_service.create_list(user.id, "Driver hidden", source_module="driver")
    await list_service.create_list(other.id, "Other list")

    reminder_service = ReminderService(db_session)
    remind_at = datetime(2026, 5, 25, 10, 0, tzinfo=timezone.utc)
    await reminder_service.create_reminder(user.id, "Web reminder", remind_at, repeat_rule=RepeatRule.NONE)
    await reminder_service.create_reminder(user.id, "Driver reminder", remind_at, source_module="driver")

    medication = Medication(user_id=user.id, name="Web medication", importance="normal", is_active=True)
    db_session.add(medication)
    await db_session.flush()
    driver_service = DriverService(db_session)
    await driver_service.create_vehicle(user.id, "Web car", current_mileage_km=1000)
    await db_session.commit()

    app = create_application()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    headers = {
        "X-Telegram-Init-Data": _telegram_init_data(
            {
                "id": user.telegram_id,
                "username": user.username,
                "first_name": user.first_name,
            }
        )
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        me_response = await client.get("/me", headers=headers)
        summary_response = await client.get("/me/summary", headers=headers)
        lists_response = await client.get("/me/lists", headers=headers)
        reminders_response = await client.get("/me/reminders", headers=headers)
        medications_response = await client.get("/me/medications", headers=headers)
        driver_response = await client.get("/me/driver", headers=headers)

    assert me_response.status_code == 200
    assert summary_response.status_code == 200
    assert lists_response.status_code == 200
    assert reminders_response.status_code == 200
    assert medications_response.status_code == 200
    assert driver_response.status_code == 200

    assert me_response.json()["telegram_id"] == user.telegram_id
    assert summary_response.json()["stats"]["lists"]["owned"] == 1
    assert [item["title"] for item in lists_response.json()] == ["Web list"]
    assert [item["text"] for item in reminders_response.json()] == ["Web reminder"]
    assert medications_response.json()[0]["name"] == "Web medication"
    assert driver_response.json()["vehicles"][0]["title"] == "Web car"


@pytest.mark.asyncio
async def test_user_api_rejects_invalid_init_data(db_session):
    """User API should not accept unsigned Telegram IDs."""
    app = create_application()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/me", headers={"X-Telegram-Init-Data": "user={\"id\":1}"})

    assert response.status_code == 401
