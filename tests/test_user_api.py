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
from src.services.web_auth_service import WebAuthService


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
        reminders_response = await client.get("/me/reminders?active_only=false", headers=headers)
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
    assert summary_response.json()["app_info"]["version"] == settings.APP_VERSION
    assert [item["title"] for item in lists_response.json()] == ["Web list"]
    assert [item["text"] for item in reminders_response.json()] == ["Web reminder"]
    assert medications_response.json()[0]["name"] == "Web medication"
    assert driver_response.json()["vehicles"][0]["title"] == "Web car"


@pytest.mark.asyncio
async def test_public_app_info_endpoint_exposes_release_metadata(db_session):
    """Web UI should be able to load version/changelog metadata before login."""
    app = create_application()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/app/info")

    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == settings.APP_VERSION
    assert payload["release_channel"]
    assert datetime.fromisoformat(payload["started_at_utc"])
    assert datetime.fromisoformat(payload["started_at_local"])
    assert payload["started_timezone"] == settings.TIMEZONE_DEFAULT
    assert payload["started_at_display"]
    assert payload["startup_announce_mode"] == settings.STARTUP_ANNOUNCE_MODE
    assert payload["startup_admin_announce_mode"] == settings.STARTUP_ADMIN_ANNOUNCE_MODE
    assert "changes" in payload
    assert payload["user_changes"] == payload["changes"]
    assert "technical_changes" in payload
    assert isinstance(payload["release_history"], list)


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


@pytest.mark.asyncio
async def test_user_api_accepts_bot_issued_web_login_key(db_session):
    """Standalone web UI should authenticate with a hashed key issued by the bot."""
    user = User(telegram_id=93501, username="web_key_user", first_name="Key", timezone="UTC")
    db_session.add(user)
    await db_session.flush()
    login_key = await WebAuthService(db_session).create_login_key(user.id)
    await db_session.commit()

    app = create_application()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/me", headers={"X-Web-Login-Token": login_key.token})
        invalid_response = await client.get("/me", headers={"X-Web-Login-Token": "invalid"})

    assert response.status_code == 200
    assert response.json()["telegram_id"] == user.telegram_id
    assert invalid_response.status_code == 401


@pytest.mark.asyncio
async def test_web_login_key_rotation_disables_previous_key(db_session):
    """Creating a new web key should make the previous key stop working."""
    user = User(telegram_id=93502, username="web_key_rotate", first_name="Rotate", timezone="UTC")
    db_session.add(user)
    await db_session.flush()
    service = WebAuthService(db_session)
    first_key = await service.create_login_key(user.id)
    second_key = await service.create_login_key(user.id)

    assert await service.authenticate(first_key.token) is None
    assert (await service.authenticate(second_key.token)).id == user.id


@pytest.mark.asyncio
async def test_web_ui_page_and_test_user_crud_api(db_session):
    """Web UI should load and perform core user-scoped mutations through services."""
    app = create_application()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    headers = {
        "X-Admin-Token": settings.ADMIN_TOKEN,
        "X-Web-Test-Telegram-Id": "94001",
        "X-Web-Test-First-Name": "Browser",
    }
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        web_response = await client.get("/web")
        summary_response = await client.get("/me/summary", headers=headers)

        list_response = await client.post("/me/lists", headers=headers, json={"title": "Web CRUD"})
        list_id = list_response.json()["id"]
        item_response = await client.post(
            f"/me/lists/{list_id}/items",
            headers=headers,
            json={"text": "first\nsecond"},
        )
        item_id = item_response.json()["items"][0]["id"]
        second_item_id = item_response.json()["items"][1]["id"]
        checklist_response = await client.post(
            f"/me/lists/{list_id}/checklist-runs",
            headers=headers,
        )
        checklist_run_id = checklist_response.json()["id"]
        checklist_item_id = checklist_response.json()["items"][0]["id"]
        checklist_toggle_response = await client.post(
            f"/me/checklist-runs/{checklist_run_id}/items/{checklist_item_id}/toggle",
            headers=headers,
        )
        active_checklist_response = await client.get(
            f"/me/lists/{list_id}/active-checklist-run",
            headers=headers,
        )
        checklist_check_all_response = await client.post(
            f"/me/checklist-runs/{checklist_run_id}/check-all",
            headers=headers,
        )
        checklist_finish_response = await client.post(
            f"/me/checklist-runs/{checklist_run_id}/finish",
            headers=headers,
        )
        checklist_fetch_response = await client.get(
            f"/me/checklist-runs/{checklist_run_id}",
            headers=headers,
        )
        toggled_response = await client.patch(
            f"/me/lists/items/{item_id}",
            headers=headers,
            json={"is_completed": True},
        )
        share_response = await client.post(f"/me/lists/{list_id}/share", headers=headers)
        members_response = await client.get(f"/me/lists/{list_id}/members", headers=headers)

        reminder_response = await client.post(
            "/me/reminders",
            headers=headers,
            json={
                "text": "Web reminder",
                "title": "Web",
                "remind_at_local": "2026-05-25T10:00:00",
                "repeat_rule": "none",
            },
        )
        reminder_id = reminder_response.json()["id"]
        updated_reminder_response = await client.patch(
            f"/me/reminders/{reminder_id}",
            headers=headers,
            json={
                "text": "Web reminder updated",
                "title": "Web updated",
                "remind_at_local": "2026-05-25T12:30:00",
                "repeat_rule": "daily",
            },
        )
        canceled_reminder_response = await client.post(
            f"/me/reminders/{reminder_id}/cancel",
            headers=headers,
        )

        medication_response = await client.post(
            "/me/medications",
            headers=headers,
            json={
                "name": "Web med",
                "dosage": "1 tablet",
                "instructions": "after meal",
                "importance": "important",
                "daily_times_local": ["09:00", "21:00"],
            },
        )
        medication_id = medication_response.json()["id"]
        updated_medication_response = await client.patch(
            f"/me/medications/{medication_id}",
            headers=headers,
            json={
                "name": "Web med updated",
                "dosage": "2 tablets",
                "instructions": "before meal",
                "importance": "critical",
                "daily_times_local": ["10:30"],
            },
        )

        vehicle_response = await client.post(
            "/me/driver/vehicles",
            headers=headers,
            json={
                "title": "Web car",
                "current_mileage_km": 1000,
                "service_interval_km": 9000,
                "service_interval_months": 10,
            },
        )
        vehicle_id = vehicle_response.json()["id"]
        updated_vehicle_response = await client.patch(
            f"/me/driver/vehicles/{vehicle_id}",
            headers=headers,
            json={
                "title": "Web car updated",
                "current_mileage_km": 1200,
                "service_interval_km": 8000,
                "service_interval_months": 8,
            },
        )
        service_done_response = await client.post(
            f"/me/driver/vehicles/{vehicle_id}/service-done",
            headers=headers,
            json={"service_mileage_km": 1250},
        )
        fuel_response = await client.post(
            f"/me/driver/vehicles/{vehicle_id}/fuel",
            headers=headers,
            json={
                "mileage_km": 1100,
                "liters": 10,
                "total_cost": 600,
                "is_full_tank": True,
            },
        )
        fuel_id = fuel_response.json()["id"]
        updated_fuel_response = await client.patch(
            f"/me/driver/fuel/{fuel_id}",
            headers=headers,
            json={
                "mileage_km": 1300,
                "liters": 12,
                "total_cost": 720,
                "is_full_tank": True,
                "station": "Test station",
                "note": "updated",
            },
        )
        expense_response = await client.post(
            "/me/driver/expenses",
            headers=headers,
            json={
                "vehicle_id": vehicle_id,
                "title": "Wash",
                "category": "wash",
                "amount": 500,
                "note": "manual",
            },
        )
        expense_id = expense_response.json()["id"]
        updated_expense_response = await client.patch(
            f"/me/driver/expenses/{expense_id}",
            headers=headers,
            json={
                "vehicle_id": vehicle_id,
                "title": "Wash updated",
                "category": "wash",
                "amount": 700,
                "note": "updated",
            },
        )
        document_response = await client.post(
            "/me/driver/documents",
            headers=headers,
            json={
                "vehicle_id": vehicle_id,
                "title": "OSAGO",
                "document_type": "insurance",
                "identifier": "test",
                "remind_before_days": 10,
            },
        )
        document_id = document_response.json()["id"]
        updated_document_response = await client.patch(
            f"/me/driver/documents/{document_id}",
            headers=headers,
            json={
                "vehicle_id": vehicle_id,
                "title": "OSAGO updated",
                "document_type": "insurance",
                "identifier": "test2",
                "remind_before_days": 7,
                "is_active": True,
            },
        )
        journal_response = await client.get("/me/driver/journal", headers=headers)
        filtered_journal_response = await client.get(
            f"/me/driver/journal?vehicle_id={vehicle_id}&event_type=wash",
            headers=headers,
        )
        manual_journal_response = await client.post(
            "/me/driver/journal",
            headers=headers,
            json={
                "vehicle_id": vehicle_id,
                "event_type": "repair",
                "title": "Manual repair",
                "description": "Changed belt",
            },
        )

        lists_response = await client.get("/me/lists", headers=headers)
        list_detail_response = await client.get(f"/me/lists/{list_id}", headers=headers)
        reminders_response = await client.get("/me/reminders?active_only=false", headers=headers)
        medications_response = await client.get("/me/medications", headers=headers)
        driver_response = await client.get("/me/driver", headers=headers)

    assert web_response.status_code == 200
    assert "RememberMe Web" in web_response.text
    assert summary_response.status_code == 200
    assert list_response.status_code == 201
    assert item_response.status_code == 201
    assert checklist_response.status_code == 201
    assert checklist_response.json()["items_total"] == 2
    assert checklist_toggle_response.json()["items_checked"] == 1
    assert active_checklist_response.status_code == 200
    assert active_checklist_response.json()["id"] == checklist_run_id
    assert checklist_check_all_response.json()["items_checked"] == 2
    assert checklist_finish_response.json()["status"] == "completed"
    assert checklist_fetch_response.json()["status"] == "completed"
    assert toggled_response.json()["items"][0]["is_completed"] is True
    assert share_response.status_code == 200
    assert share_response.json()["import_command"].startswith("/import_list ")
    assert members_response.status_code == 200
    assert members_response.json()[0]["role"] == "owner"
    assert reminder_response.status_code == 201
    assert updated_reminder_response.json()["text"] == "Web reminder updated"
    assert updated_reminder_response.json()["repeat_rule"] == "daily"
    assert canceled_reminder_response.json()["status"] == "canceled"
    assert medication_response.status_code == 201
    assert medication_response.json()["daily_times_local"] == ["09:00", "21:00"]
    assert updated_medication_response.json()["name"] == "Web med updated"
    assert updated_medication_response.json()["importance"] == "critical"
    assert updated_medication_response.json()["daily_times_local"] == ["10:30"]
    assert vehicle_response.status_code == 201
    assert updated_vehicle_response.json()["title"] == "Web car updated"
    assert updated_vehicle_response.json()["service_interval_km"] == 8000
    assert service_done_response.json()["last_service_mileage_km"] == 1250
    assert fuel_response.status_code == 201
    assert updated_fuel_response.json()["mileage_km"] == 1300
    assert updated_fuel_response.json()["note"] == "updated"
    assert expense_response.status_code == 201
    assert updated_expense_response.json()["title"] == "Wash updated"
    assert updated_expense_response.json()["amount"] == 700
    assert document_response.status_code == 201
    assert updated_document_response.json()["title"] == "OSAGO updated"
    assert updated_document_response.json()["remind_before_days"] == 7
    assert journal_response.status_code == 200
    assert filtered_journal_response.status_code == 200
    assert manual_journal_response.status_code == 201
    journal_event_types = {item["event_type"] for item in journal_response.json()}
    assert {"service_done", "fuel_entry", "fuel_entry_updated", "wash", "document", "document_updated"}.issubset(
        journal_event_types
    )
    assert filtered_journal_response.json()
    assert all(item["event_type"] == "wash" for item in filtered_journal_response.json())
    assert manual_journal_response.json()["event_type"] == "repair"
    assert manual_journal_response.json()["vehicle_id"] == vehicle_id
    assert lists_response.json()[0]["title"] == "Web CRUD"
    assert next(item for item in list_detail_response.json()["items"] if item["id"] == second_item_id)["is_completed"] is False
    assert reminders_response.json()[0]["status"] == "canceled"
    assert medications_response.json()[0]["name"] == "Web med updated"
    assert driver_response.json()["overview"]["vehicles_count"] == 1
    assert driver_response.json()["overview"]["fuel_entries_count"] == 1
    assert driver_response.json()["overview"]["expense_entries_count"] == 1
    assert driver_response.json()["overview"]["documents_active_count"] == 1
    assert driver_response.json()["overview"]["journal_entries_count"] >= 7
    assert any(item["title"] == "Manual repair" for item in driver_response.json()["journal"])
    assert driver_response.json()["expenses"][0]["title"] == "Wash updated"
    assert driver_response.json()["documents"][0]["title"] == "OSAGO updated"


@pytest.mark.asyncio
async def test_web_medication_response_exposes_mark_availability(db_session):
    """Web medications should tell UI when intake buttons must be disabled."""
    app = create_application()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    headers = {
        "X-Admin-Token": settings.ADMIN_TOKEN,
        "X-Web-Test-Telegram-Id": "94002",
        "X-Web-Test-First-Name": "Medication",
    }
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        medication_response = await client.post(
            "/me/medications",
            headers=headers,
            json={"name": "Once daily", "daily_times_local": []},
        )
        medication_id = medication_response.json()["id"]
        assert medication_response.json()["can_mark_now"] is True

        taken_response = await client.post(f"/me/medications/{medication_id}/taken", headers=headers)
        medications_response = await client.get("/me/medications", headers=headers)

    item = medications_response.json()[0]
    assert taken_response.json()["ok"] is True
    assert item["can_mark_now"] is False
    assert item["marked_at_utc"]
    assert item["next_available_at_utc"]
    assert item["today_slots"][0]["label"] == "Сегодня"
    assert item["today_slots"][0]["status"] == "taken"
    assert item["today_slots"][0]["status_label"] == "принято"
