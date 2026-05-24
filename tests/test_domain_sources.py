"""Domain-source isolation tests."""

from datetime import datetime, timezone

import pytest

from src.db.models import Medication, ReminderStatus, RepeatRule, User
from src.services.driver_service import DriverService
from src.services.list_service import ListService
from src.services.reminder_service import ReminderService
from src.services.settings_service import SettingsService


@pytest.mark.asyncio
async def test_generic_lists_hide_driver_templates(db_session):
    """Driver checklists should not pollute the generic lists screen."""
    user = User(telegram_id=91001, timezone="UTC")
    db_session.add(user)
    await db_session.flush()

    service = ListService(db_session)
    general = await service.create_list(user.id, "Обычный список")
    driver = await service.create_list(user.id, "🚗 Запчасти к покупке", source_module="driver")

    lists, total = await service.get_lists_list(user.id)

    assert total == 1
    assert [item.id for item in lists] == [general.id]
    assert driver.id not in [item.id for item in lists]


@pytest.mark.asyncio
async def test_generic_reminders_hide_list_medication_and_driver_domains(db_session):
    """Generic reminders should show only standalone user reminders."""
    user = User(telegram_id=91002, timezone="UTC")
    db_session.add(user)
    await db_session.flush()

    list_service = ListService(db_session)
    reminder_service = ReminderService(db_session)
    todo_list = await list_service.create_list(user.id, "Список")
    medication = Medication(user_id=user.id, name="Лекарство", importance="normal")
    db_session.add(medication)
    await db_session.flush()
    remind_at = datetime(2026, 5, 24, 10, 0, tzinfo=timezone.utc)

    general = await reminder_service.create_reminder(
        user_id=user.id,
        text="Обычное напоминание",
        remind_at_utc=remind_at,
        repeat_rule=RepeatRule.NONE,
    )
    list_reminder = await reminder_service.create_reminder(
        user_id=user.id,
        text="Напомнить про список",
        remind_at_utc=remind_at,
        list_id=todo_list.id,
    )
    med_reminder = await reminder_service.create_reminder(
        user_id=user.id,
        text="Принять лекарство",
        remind_at_utc=remind_at,
        medication_id=medication.id,
    )
    driver_reminder = await reminder_service.create_reminder(
        user_id=user.id,
        text="Проверить давление в шинах",
        remind_at_utc=remind_at,
        source_module="driver",
    )

    reminders, total = await reminder_service.get_reminders_list(user.id)
    all_reminders, all_total = await reminder_service.get_reminders_list(user.id, source_module=None)

    assert total == 1
    assert [item.id for item in reminders] == [general.id]
    assert list_reminder.source_module == "list"
    assert med_reminder.source_module == "medication"
    assert driver_reminder.source_module == "driver"
    assert all_total == 4
    assert {item.id for item in all_reminders} == {
        general.id,
        list_reminder.id,
        med_reminder.id,
        driver_reminder.id,
    }


@pytest.mark.asyncio
async def test_settings_stats_separate_generic_and_admin_activity(db_session):
    """Settings stats should show clean personal counts and admin aggregate activity."""
    admin = User(telegram_id=91003, timezone="UTC", is_admin=True)
    other = User(telegram_id=91004, timezone="UTC")
    db_session.add_all([admin, other])
    await db_session.flush()

    list_service = ListService(db_session)
    reminder_service = ReminderService(db_session)
    await list_service.create_list(admin.id, "Админский список")
    await list_service.create_list(admin.id, "🚗 Проверка перед поездкой", source_module="driver")
    await list_service.create_list(other.id, "Пользовательский список")

    medication = Medication(user_id=other.id, name="Магний", importance="normal")
    db_session.add(medication)
    await db_session.flush()

    remind_at = datetime(2026, 5, 24, 10, 0, tzinfo=timezone.utc)
    await reminder_service.create_reminder(admin.id, "Обычное", remind_at, repeat_rule=RepeatRule.NONE)
    await reminder_service.create_reminder(
        other.id,
        "Лекарство",
        remind_at,
        medication_id=medication.id,
    )

    driver_service = DriverService(db_session)
    vehicle = await driver_service.create_vehicle(other.id, "Авто", current_mileage_km=1000)
    await driver_service.add_fuel_entry(other.id, vehicle.id, 1200, 20, 1200, True)

    settings_service = SettingsService(db_session)
    stats = await settings_service.get_stats(admin.id)
    admin_activity = await settings_service.get_admin_activity_stats(admin.id)

    assert stats["lists"]["owned"] == 1
    assert stats["reminders"]["active"] == 1
    assert stats["driver"]["vehicles_count"] == 0
    assert admin_activity["users"]["other"] == 1
    assert admin_activity["lists"]["other_users"] == 1
    assert admin_activity["medications"]["other_users"] == 1
    assert admin_activity["driver"]["vehicle_users"] == 1
    assert admin_activity["driver"]["fuel_entries"] == 1
