"""Tests for driver assistant service."""

import pytest
from datetime import datetime, timezone

from src.db.models import User
from src.services.driver_service import DriverService


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
