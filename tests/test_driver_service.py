"""Tests for driver assistant service."""

import pytest
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from src.db.models import Reminder, ReminderStatus, User
from src.services.checklist_service import ChecklistService
from src.services.driver_service import DriverService
from src.services.list_service import ListService
from src.services.vehicle_presets import get_vehicle_preset, list_vehicle_presets


def _as_utc(value: datetime) -> datetime:
    """SQLite test backend may return timezone-aware columns as naive UTC."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_driver_vehicle_profile_and_mileage_update(db_session):
    """Vehicle profiles store mileage and service intervals."""
    user = User(telegram_id=7001, timezone="Europe/Moscow")
    db_session.add(user)
    await db_session.flush()

    service = DriverService(db_session)
    vehicle = await service.create_vehicle(
        user_id=user.id,
        title="Toyota Camry 2018",
        current_mileage_km=125000,
        service_interval_km=10000,
        service_interval_months=12,
    )

    updated = await service.update_mileage(vehicle.id, user.id, 126500)

    assert updated is not None
    assert updated.current_mileage_km == 126500
    assert updated.service_interval_km == 10000


def test_vehicle_presets_include_requested_variants():
    """Curated presets should expose all requested cars as direct choices."""
    slugs = {preset.slug for preset in list_vehicle_presets()}

    assert "hyundai_verna_2007_1_4_mt" in slugs
    assert "lada_niva_21213_1997_1_7_mt" in slugs
    assert "lada_niva_21214_1_7_mt" in slugs
    assert "ford_focus_2_hatchback_1_6_100_mt" in slugs
    assert "ford_focus_2_hatchback_1_6_115_mt" in slugs
    assert "mitsubishi_pajero_pinin_1_8_mt_awd" in slugs
    assert "mitsubishi_pajero_pinin_2_0_mt_awd" in slugs
    assert "lada_kalina_1118_2008_1_6_8v_mt" in slugs


@pytest.mark.asyncio
async def test_fuel_entry_calculates_consumption_after_second_full_tank(db_session):
    """Consumption is calculated from full-tank mileage distance."""
    user = User(telegram_id=7002, timezone="Europe/Moscow")
    db_session.add(user)
    await db_session.flush()

    service = DriverService(db_session)
    vehicle = await service.create_vehicle(
        user_id=user.id,
        title="Honda Fit",
        current_mileage_km=100000,
    )

    first = await service.add_fuel_entry(
        user_id=user.id,
        vehicle_id=vehicle.id,
        mileage_km=100000,
        liters=40,
        total_cost=2400,
        is_full_tank=True,
    )
    second = await service.add_fuel_entry(
        user_id=user.id,
        vehicle_id=vehicle.id,
        mileage_km=100500,
        liters=35,
        total_cost=2100,
        is_full_tank=True,
    )

    assert first.consumption_l_per_100 is None
    assert second.consumption_l_per_100 == pytest.approx(7.0)
    assert second.cost_per_km == pytest.approx(4.2)

    summary = await service.get_fuel_summary(user.id)

    assert summary["count"] == 2
    assert summary["avg_consumption"] == pytest.approx(7.0)


@pytest.mark.asyncio
async def test_fuel_entry_includes_partial_refuels_between_full_tanks(db_session):
    """Partial refuels between full tanks should be included in interval stats."""
    user = User(telegram_id=7003, timezone="Europe/Moscow")
    db_session.add(user)
    await db_session.flush()

    service = DriverService(db_session)
    vehicle = await service.create_vehicle(
        user_id=user.id,
        title="Mazda 3",
        current_mileage_km=50000,
    )

    await service.add_fuel_entry(
        user_id=user.id,
        vehicle_id=vehicle.id,
        mileage_km=50000,
        liters=45,
        total_cost=2700,
        is_full_tank=True,
    )
    partial = await service.add_fuel_entry(
        user_id=user.id,
        vehicle_id=vehicle.id,
        mileage_km=50300,
        liters=10,
        total_cost=600,
        is_full_tank=False,
    )
    second_full = await service.add_fuel_entry(
        user_id=user.id,
        vehicle_id=vehicle.id,
        mileage_km=50600,
        liters=35,
        total_cost=2100,
        is_full_tank=True,
    )

    assert partial.consumption_l_per_100 is None
    assert second_full.consumption_l_per_100 == pytest.approx(7.5)
    assert second_full.cost_per_km == pytest.approx(4.5)


@pytest.mark.asyncio
async def test_driver_service_rejects_cross_user_vehicle_mutations(db_session):
    """A user must not mutate another user's vehicle by guessing IDs."""
    owner = User(telegram_id=7004, timezone="Europe/Moscow")
    other = User(telegram_id=7005, timezone="Europe/Moscow")
    db_session.add_all([owner, other])
    await db_session.flush()

    service = DriverService(db_session)
    vehicle = await service.create_vehicle(
        user_id=owner.id,
        title="Owner car",
        current_mileage_km=1000,
    )

    mileage_result = await service.update_mileage(vehicle.id, other.id, 2000)
    fuel_result = await service.add_fuel_entry(
        user_id=other.id,
        vehicle_id=vehicle.id,
        mileage_km=2000,
        liters=30,
        total_cost=1800,
        is_full_tank=True,
    )

    owner_vehicle = await service.get_vehicle(vehicle.id, owner.id)
    other_vehicle = await service.get_vehicle(vehicle.id, other.id)
    owner_entries = await service.get_fuel_entries(owner.id)
    other_entries = await service.get_fuel_entries(other.id)

    assert mileage_result is None
    assert fuel_result is None
    assert owner_vehicle.current_mileage_km == 1000
    assert other_vehicle is None
    assert owner_entries == []
    assert other_entries == []


@pytest.mark.asyncio
async def test_fuel_history_recalculates_after_update_and_delete(db_session):
    """Fuel edits and deletes should recalculate dependent consumption values."""
    user = User(telegram_id=7006, timezone="Europe/Moscow")
    db_session.add(user)
    await db_session.flush()

    service = DriverService(db_session)
    vehicle = await service.create_vehicle(user_id=user.id, title="Recalc car")
    await service.add_fuel_entry(user.id, vehicle.id, 1000, 40, 2400, True)
    partial = await service.add_fuel_entry(user.id, vehicle.id, 1300, 10, 600, False)
    second_full = await service.add_fuel_entry(user.id, vehicle.id, 1600, 35, 2100, True)

    assert second_full.consumption_l_per_100 == pytest.approx(7.5)

    updated = await service.update_fuel_entry(
        entry_id=partial.id,
        user_id=user.id,
        mileage_km=1300,
        liters=20,
        total_cost=1200,
        is_full_tank=False,
    )
    second_full = await service.get_fuel_entry(second_full.id, user.id)

    assert updated is not None
    assert second_full.consumption_l_per_100 == pytest.approx(55 / 600 * 100)
    assert second_full.cost_per_km == pytest.approx(3300 / 600)

    assert await service.delete_fuel_entry(partial.id, user.id) is True
    second_full = await service.get_fuel_entry(second_full.id, user.id)

    assert second_full.consumption_l_per_100 == pytest.approx(35 / 600 * 100)
    assert second_full.cost_per_km == pytest.approx(2100 / 600)


@pytest.mark.asyncio
async def test_fuel_entry_update_down_recalculates_vehicle_current_mileage(db_session):
    """Editing the highest fuel mileage down should lower derived current mileage."""
    user = User(telegram_id=7008, timezone="Europe/Moscow")
    db_session.add(user)
    await db_session.flush()

    service = DriverService(db_session)
    vehicle = await service.create_vehicle(user_id=user.id, title="Mileage car", current_mileage_km=1000)
    entry = await service.add_fuel_entry(user.id, vehicle.id, 2000, 40, 2400, True)

    assert vehicle.current_mileage_km == 2000

    updated = await service.update_fuel_entry(
        entry_id=entry.id,
        user_id=user.id,
        mileage_km=1500,
        liters=40,
        total_cost=2400,
        is_full_tank=True,
    )
    vehicle = await service.get_vehicle(vehicle.id, user.id)

    assert updated is not None
    assert vehicle.manual_mileage_km == 1000
    assert vehicle.current_mileage_km == 1500


@pytest.mark.asyncio
async def test_fuel_entry_delete_max_recalculates_vehicle_current_mileage(db_session):
    """Deleting the highest fuel mileage should fall back to next fuel entry or manual mileage."""
    user = User(telegram_id=7009, timezone="Europe/Moscow")
    db_session.add(user)
    await db_session.flush()

    service = DriverService(db_session)
    vehicle = await service.create_vehicle(user_id=user.id, title="Delete mileage car", current_mileage_km=1000)
    lower = await service.add_fuel_entry(user.id, vehicle.id, 1500, 30, 1800, True)
    higher = await service.add_fuel_entry(user.id, vehicle.id, 2000, 35, 2100, True)

    assert vehicle.current_mileage_km == 2000

    assert await service.delete_fuel_entry(higher.id, user.id) is True
    vehicle = await service.get_vehicle(vehicle.id, user.id)
    assert vehicle.current_mileage_km == 1500

    assert await service.delete_fuel_entry(lower.id, user.id) is True
    vehicle = await service.get_vehicle(vehicle.id, user.id)
    assert vehicle.current_mileage_km == 1000


@pytest.mark.asyncio
async def test_driver_service_rejects_invalid_vehicle_and_fuel_values(db_session):
    """Service layer should reject invalid values even if handlers are bypassed."""
    user = User(telegram_id=7010, timezone="Europe/Moscow")
    db_session.add(user)
    await db_session.flush()

    service = DriverService(db_session)

    with pytest.raises(ValueError):
        await service.create_vehicle(user.id, "Bad mileage", current_mileage_km=-1)
    with pytest.raises(ValueError):
        await service.create_vehicle(user.id, "Bad interval", service_interval_km=0)
    with pytest.raises(ValueError):
        await service.create_vehicle(user.id, "Bad months", service_interval_months=0)
    with pytest.raises(ValueError):
        await service.create_vehicle(user.id, "Bad engine", engine_volume_l=0)
    with pytest.raises(ValueError):
        await service.create_vehicle(user.id, "Bad expected consumption", expected_consumption_mixed_l_per_100=-1)

    vehicle = await service.create_vehicle(user.id, "Valid car", current_mileage_km=1000)

    invalid_values = [
        {"mileage_km": -1, "liters": 10, "total_cost": 1000},
        {"mileage_km": 1000, "liters": 0, "total_cost": 1000},
        {"mileage_km": 1000, "liters": 10, "total_cost": 0},
    ]
    for values in invalid_values:
        with pytest.raises(ValueError):
            await service.add_fuel_entry(user.id, vehicle.id, **values)

    entry = await service.add_fuel_entry(user.id, vehicle.id, 1100, 10, 1000, True)
    with pytest.raises(ValueError):
        await service.update_fuel_entry(entry.id, user.id, 1200, -5, 1000, True)


@pytest.mark.asyncio
async def test_driver_vehicle_stores_preset_snapshot(db_session):
    """Vehicle presets should be copied into user-owned vehicle snapshots."""
    user = User(telegram_id=7011, timezone="Europe/Moscow")
    db_session.add(user)
    await db_session.flush()

    preset = get_vehicle_preset("lada_kalina_1118_2008_1_6_8v_mt")
    assert preset is not None

    service = DriverService(db_session)
    vehicle = await service.create_vehicle(
        user_id=user.id,
        title=preset.title,
        current_mileage_km=123000,
        service_interval_km=preset.service_interval_km,
        service_interval_months=preset.service_interval_months,
        **preset.vehicle_kwargs(),
    )

    assert vehicle.preset_slug == preset.slug
    assert vehicle.make == "Lada"
    assert vehicle.model == "Kalina 1118"
    assert vehicle.engine_volume_l == pytest.approx(1.6)
    assert vehicle.engine_power_hp == 81
    assert vehicle.expected_consumption_mixed_l_per_100 == pytest.approx(7.1)


@pytest.mark.asyncio
async def test_vehicle_update_delete_and_service_plan(db_session):
    """Vehicle profile supports editing, deletion, and service planning."""
    user = User(telegram_id=7007, timezone="Europe/Moscow")
    db_session.add(user)
    await db_session.flush()

    service = DriverService(db_session)
    vehicle = await service.create_vehicle(user_id=user.id, title="Old title", current_mileage_km=10000)

    updated = await service.update_vehicle(
        vehicle_id=vehicle.id,
        user_id=user.id,
        title="New title",
        current_mileage_km=12000,
        service_interval_km=8000,
        service_interval_months=6,
    )
    serviced = await service.mark_service_done(
        vehicle_id=vehicle.id,
        user_id=user.id,
        service_mileage_km=12000,
        serviced_at_utc=datetime(2026, 1, 15, tzinfo=timezone.utc),
    )
    plan = await service.get_service_plan(
        vehicle.id,
        user.id,
        now_utc=datetime(2026, 4, 1, tzinfo=timezone.utc),
    )

    assert updated.title == "New title"
    assert serviced.last_service_mileage_km == 12000
    assert plan["next_mileage"] == 20000
    assert plan["remaining_km"] == 8000
    assert plan["date_status"] == "ok"

    assert await service.delete_vehicle(vehicle.id, user.id) is True
    assert await service.get_vehicle(vehicle.id, user.id) is None


@pytest.mark.asyncio
async def test_driver_expenses_and_documents_are_user_owned(db_session):
    """Manual expenses and documents should be autonomous and user-owned."""
    owner = User(telegram_id=7011, timezone="Europe/Moscow")
    other = User(telegram_id=7012, timezone="Europe/Moscow")
    db_session.add_all([owner, other])
    await db_session.flush()

    service = DriverService(db_session)
    vehicle = await service.create_vehicle(owner.id, "Owner car", current_mileage_km=1000)

    expense = await service.create_expense(
        owner.id,
        title="Wash",
        amount=500,
        category="wash",
        vehicle_id=vehicle.id,
    )
    document = await service.create_document(
        owner.id,
        title="OSAGO",
        document_type="insurance",
        vehicle_id=vehicle.id,
        remind_before_days=10,
    )
    overview = await service.get_user_overview(owner.id)

    assert expense is not None
    assert document is not None
    assert overview["expense_entries_count"] == 1
    assert overview["expense_total_cost"] == 500
    assert overview["documents_active_count"] == 1

    assert await service.create_expense(other.id, "Bad", 100, vehicle_id=vehicle.id) is None
    assert await service.create_document(other.id, "Bad doc", vehicle_id=vehicle.id) is None
    assert await service.get_expense(expense.id, other.id) is None
    assert await service.get_document(document.id, other.id) is None

    with pytest.raises(ValueError):
        await service.create_expense(owner.id, "Bad amount", 0)
    with pytest.raises(ValueError):
        await service.create_document(owner.id, "Bad remind", remind_before_days=-1)


@pytest.mark.asyncio
async def test_driver_document_syncs_active_reminder(db_session):
    """Driver documents with expiry should create, update, and cancel linked reminders."""
    user = User(telegram_id=7013, timezone="Europe/Moscow")
    db_session.add(user)
    await db_session.flush()

    service = DriverService(db_session)
    expires_at = datetime(2026, 6, 20, 9, 0, tzinfo=timezone.utc)
    document = await service.create_document(
        user.id,
        "OSAGO",
        document_type="insurance",
        expires_at_utc=expires_at,
        remind_before_days=10,
    )

    result = await db_session.execute(
        select(Reminder).where(
            Reminder.driver_document_id == document.id,
            Reminder.status == ReminderStatus.ACTIVE,
        )
    )
    reminder = result.scalar_one()
    assert reminder.source_module == "driver"
    assert _as_utc(reminder.remind_at_utc) == expires_at - timedelta(days=10)
    assert "OSAGO" in reminder.text

    updated_expires_at = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
    await service.update_document(
        document.id,
        user.id,
        title="OSAGO updated",
        document_type="insurance",
        expires_at_utc=updated_expires_at,
        remind_before_days=7,
    )

    result = await db_session.execute(
        select(Reminder).where(Reminder.driver_document_id == document.id)
    )
    reminders = result.scalars().all()
    active = [item for item in reminders if item.status == ReminderStatus.ACTIVE]
    canceled = [item for item in reminders if item.status == ReminderStatus.CANCELED]
    assert len(active) == 1
    assert len(canceled) == 1
    assert _as_utc(active[0].remind_at_utc) == updated_expires_at - timedelta(days=7)

    assert await service.delete_document(document.id, user.id) is True
    result = await db_session.execute(
        select(Reminder).where(
            Reminder.driver_document_id == document.id,
            Reminder.status == ReminderStatus.ACTIVE,
        )
    )
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_driver_checklist_completion_creates_journal_entry(db_session):
    """Completed driver checklists should be fixed in the autonomous driver journal."""
    user = User(telegram_id=7016, timezone="Europe/Moscow")
    db_session.add(user)
    await db_session.flush()

    list_service = ListService(db_session)
    checklist_service = ChecklistService(db_session)
    driver_service = DriverService(db_session)
    vehicle = await driver_service.create_vehicle(
        user_id=user.id,
        title="Checklist car",
        current_mileage_km=1000,
    )

    todo_list = await list_service.create_list(user.id, "Проверка жидкостей", source_module="driver")
    await list_service.add_items_bulk(
        todo_list.id,
        user.id,
        ["Моторное масло", "Антифриз", "Тормозная жидкость"],
        source_module="driver",
    )

    run = await checklist_service.create_run_from_list(
        todo_list.id,
        user.id,
        source_module="driver",
        driver_vehicle_id=vehicle.id,
    )
    assert run is not None
    run = await checklist_service.check_all(run.id, user.id)
    assert run is not None
    finished = await checklist_service.finish_run(run.id, user.id)
    assert finished is not None

    entry = await driver_service.record_checklist_completion(finished.id, user.id)
    duplicate = await driver_service.record_checklist_completion(finished.id, user.id)
    entries = await driver_service.get_journal_entries(user.id)
    overview = await driver_service.get_user_overview(user.id)

    assert entry is not None
    assert duplicate is not None
    assert duplicate.id == entry.id
    assert len(entries) == 1
    assert entries[0].vehicle_id == vehicle.id
    assert entries[0].event_type == "fluids_check"
    assert entries[0].title == "Проверка жидкостей пройдена"
    assert entries[0].description == "Выполнено 3/3 пунктов."
    assert entries[0].metadata_json["items"] == ["Моторное масло", "Антифриз", "Тормозная жидкость"]
    vehicle_entries = await driver_service.get_journal_entries(user.id, vehicle_id=vehicle.id)
    assert [item.id for item in vehicle_entries] == [entry.id]
    assert overview["journal_entries_count"] == 1


@pytest.mark.asyncio
async def test_driver_journal_collects_vehicle_events_and_filters(db_session):
    """Fuel, expenses, documents, service, and manual notes should be visible in journal filters."""
    user = User(telegram_id=7017, timezone="Europe/Moscow")
    db_session.add(user)
    await db_session.flush()

    service = DriverService(db_session)
    vehicle = await service.create_vehicle(
        user_id=user.id,
        title="Journal car",
        current_mileage_km=1000,
    )
    fuel = await service.add_fuel_entry(
        user_id=user.id,
        vehicle_id=vehicle.id,
        mileage_km=1200,
        liters=20,
        total_cost=1100,
        is_full_tank=True,
    )
    await service.update_fuel_entry(
        fuel.id,
        user.id,
        mileage_km=1250,
        liters=22,
        total_cost=1210,
        is_full_tank=True,
    )
    await service.create_expense(
        user_id=user.id,
        vehicle_id=vehicle.id,
        title="Wash",
        category="wash",
        amount=500,
    )
    await service.create_document(
        user_id=user.id,
        vehicle_id=vehicle.id,
        title="OSAGO",
        document_type="insurance",
    )
    await service.mark_service_done(vehicle.id, user.id, service_mileage_km=1300)
    manual = await service.create_journal_entry(
        user_id=user.id,
        vehicle_id=vehicle.id,
        event_type="repair",
        title="Manual repair",
        status="note",
    )

    entries = await service.get_journal_entries(user.id, vehicle_id=vehicle.id, limit=20)
    event_types = {item.event_type for item in entries}
    wash_entries = await service.get_journal_entries(user.id, event_type="wash")
    repair_entries = await service.get_journal_entries(user.id, event_type="repair")
    overview = await service.get_user_overview(user.id)

    assert manual is not None
    assert {
        "fuel_entry",
        "fuel_entry_updated",
        "wash",
        "document",
        "service_done",
        "repair",
    }.issubset(event_types)
    assert all(item.vehicle_id == vehicle.id for item in entries)
    assert [item.event_type for item in wash_entries] == ["wash"]
    assert [item.id for item in repair_entries] == [manual.id]
    assert overview["journal_entries_count"] >= 6


@pytest.mark.asyncio
async def test_driver_journal_manual_entries_can_be_updated_and_canceled(db_session):
    """Manual journal entries should be editable and hidden after soft delete."""
    user = User(telegram_id=7018, timezone="Europe/Moscow")
    db_session.add(user)
    await db_session.flush()

    service = DriverService(db_session)
    vehicle = await service.create_vehicle(user.id, "Manual journal car", current_mileage_km=1000)
    entry = await service.create_journal_entry(
        user_id=user.id,
        vehicle_id=vehicle.id,
        event_type="note",
        title="Old note",
        description="old",
        status="note",
        metadata={"manual": True},
    )
    assert entry is not None

    updated = await service.update_journal_entry(
        entry.id,
        user.id,
        title="Updated repair",
        event_type="repair",
        vehicle_id=None,
        description="new text",
    )
    assert updated is not None
    assert updated.title == "Updated repair"
    assert updated.event_type == "repair"
    assert updated.vehicle_id is None
    assert updated.description == "new text"
    assert updated.metadata_json["edited_at_utc"]

    assert await service.cancel_journal_entry(entry.id, user.id) is True
    visible_entries = await service.get_journal_entries(user.id)
    all_entries = await service.get_journal_entries(user.id, include_canceled=True)

    assert visible_entries == []
    assert all_entries[0].status == "canceled"
    assert all_entries[0].metadata_json["canceled_at_utc"]
    assert await service.cancel_journal_entry(entry.id, user.id) is False


@pytest.mark.asyncio
async def test_driver_journal_rejects_unknown_event_types_and_protects_automatic_entries(db_session):
    """Service should whitelist journal types and keep automatic entries immutable."""
    user = User(telegram_id=7019, timezone="Europe/Moscow")
    db_session.add(user)
    await db_session.flush()

    service = DriverService(db_session)
    vehicle = await service.create_vehicle(user.id, "Automatic journal car", current_mileage_km=1000)

    with pytest.raises(ValueError):
        await service.create_journal_entry(
            user_id=user.id,
            vehicle_id=vehicle.id,
            event_type="unknown_type",
            title="Bad event",
        )

    automatic = await service.create_journal_entry(
        user_id=user.id,
        vehicle_id=vehicle.id,
        event_type="wash",
        title="Automatic wash",
        metadata={"quick_action": True},
    )

    assert automatic is not None
    assert await service.update_journal_entry(automatic.id, user.id, title="Changed") is None
    assert await service.cancel_journal_entry(automatic.id, user.id) is False
