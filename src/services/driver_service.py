"""Driver assistant business logic."""

from calendar import monthrange
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import DriverFuelEntry, DriverVehicle


class DriverService:
    """Service for vehicle profiles and fuel journal entries."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_vehicle(
        self,
        user_id: int,
        title: str,
        current_mileage_km: int = 0,
        service_interval_km: int = 10000,
        service_interval_months: int = 12,
        make: Optional[str] = None,
        model: Optional[str] = None,
        year: Optional[int] = None,
    ) -> DriverVehicle:
        """Create a vehicle profile."""
        vehicle = DriverVehicle(
            user_id=user_id,
            title=title,
            make=make,
            model=model,
            year=year,
            current_mileage_km=max(0, current_mileage_km),
            service_interval_km=max(1, service_interval_km),
            service_interval_months=max(1, service_interval_months),
        )
        self.db.add(vehicle)
        await self.db.flush()
        await self.db.refresh(vehicle)
        return vehicle

    async def get_vehicle(self, vehicle_id: int, user_id: int) -> Optional[DriverVehicle]:
        """Return a vehicle owned by the user."""
        result = await self.db.execute(
            select(DriverVehicle).where(
                DriverVehicle.id == vehicle_id,
                DriverVehicle.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_vehicles(self, user_id: int) -> list[DriverVehicle]:
        """Return user's vehicles."""
        result = await self.db.execute(
            select(DriverVehicle)
            .where(DriverVehicle.user_id == user_id)
            .order_by(DriverVehicle.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_vehicle(
        self,
        vehicle_id: int,
        user_id: int,
        title: str,
        current_mileage_km: int,
        service_interval_km: int,
        service_interval_months: int,
    ) -> Optional[DriverVehicle]:
        """Update a vehicle profile owned by the user."""
        vehicle = await self.get_vehicle(vehicle_id, user_id)
        if not vehicle:
            return None

        vehicle.title = title
        vehicle.current_mileage_km = max(0, current_mileage_km)
        vehicle.service_interval_km = max(1, service_interval_km)
        vehicle.service_interval_months = max(1, service_interval_months)
        vehicle.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(vehicle)
        return vehicle

    async def delete_vehicle(self, vehicle_id: int, user_id: int) -> bool:
        """Delete a vehicle profile owned by the user."""
        vehicle = await self.get_vehicle(vehicle_id, user_id)
        if not vehicle:
            return False

        await self.db.delete(vehicle)
        await self.db.flush()
        return True

    async def update_mileage(
        self,
        vehicle_id: int,
        user_id: int,
        mileage_km: int,
    ) -> Optional[DriverVehicle]:
        """Update current vehicle mileage."""
        vehicle = await self.get_vehicle(vehicle_id, user_id)
        if not vehicle:
            return None

        vehicle.current_mileage_km = max(0, mileage_km)
        vehicle.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(vehicle)
        return vehicle

    async def add_fuel_entry(
        self,
        user_id: int,
        vehicle_id: int,
        mileage_km: int,
        liters: float,
        total_cost: float,
        is_full_tank: bool = True,
        station: Optional[str] = None,
        note: Optional[str] = None,
    ) -> Optional[DriverFuelEntry]:
        """Add a fuel entry and calculate consumption when possible."""
        vehicle = await self.get_vehicle(vehicle_id, user_id)
        if not vehicle:
            return None

        previous_full = await self._get_previous_full_fuel_entry(
            user_id,
            vehicle_id,
            before_mileage_km=mileage_km,
        )
        distance_km = None
        consumption = None
        cost_per_km = None
        if is_full_tank and previous_full and mileage_km > previous_full.mileage_km:
            distance_km = mileage_km - previous_full.mileage_km
            interval_liters, interval_cost = await self._get_interval_fuel_totals(
                user_id=user_id,
                vehicle_id=vehicle_id,
                after_mileage_km=previous_full.mileage_km,
                before_mileage_km=mileage_km,
            )
            interval_liters += liters
            interval_cost += total_cost
            consumption = interval_liters / distance_km * 100
            cost_per_km = interval_cost / distance_km

        entry = DriverFuelEntry(
            user_id=user_id,
            vehicle_id=vehicle_id,
            mileage_km=max(0, mileage_km),
            liters=liters,
            total_cost=total_cost,
            price_per_liter=total_cost / liters if liters > 0 else None,
            is_full_tank=is_full_tank,
            station=station,
            note=note,
            consumption_l_per_100=consumption,
            cost_per_km=cost_per_km,
        )
        self.db.add(entry)

        if mileage_km > vehicle.current_mileage_km:
            vehicle.current_mileage_km = mileage_km
            vehicle.updated_at = datetime.now(timezone.utc)

        await self.db.flush()
        await self._recalculate_vehicle_fuel_stats(user_id, vehicle_id)
        await self.db.refresh(entry)
        return entry

    async def get_fuel_entries(
        self,
        user_id: int,
        vehicle_id: Optional[int] = None,
        limit: int = 5,
        offset: int = 0,
    ) -> list[DriverFuelEntry]:
        """Return recent fuel entries."""
        query = select(DriverFuelEntry).where(DriverFuelEntry.user_id == user_id)
        if vehicle_id is not None:
            query = query.where(DriverFuelEntry.vehicle_id == vehicle_id)
        query = (
            query.order_by(DriverFuelEntry.mileage_km.desc(), DriverFuelEntry.id.desc())
            .offset(max(0, offset))
            .limit(limit)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_fuel_entries(self, user_id: int, vehicle_id: Optional[int] = None) -> int:
        """Count fuel entries visible to a user."""
        query = select(func.count(DriverFuelEntry.id)).where(DriverFuelEntry.user_id == user_id)
        if vehicle_id is not None:
            query = query.where(DriverFuelEntry.vehicle_id == vehicle_id)
        result = await self.db.execute(query)
        return int(result.scalar_one() or 0)

    async def get_fuel_entry(self, entry_id: int, user_id: int) -> Optional[DriverFuelEntry]:
        """Return a fuel entry owned by the user."""
        result = await self.db.execute(
            select(DriverFuelEntry).where(
                DriverFuelEntry.id == entry_id,
                DriverFuelEntry.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def update_fuel_entry(
        self,
        entry_id: int,
        user_id: int,
        mileage_km: int,
        liters: float,
        total_cost: float,
        is_full_tank: bool,
        station: Optional[str] = None,
    ) -> Optional[DriverFuelEntry]:
        """Update a fuel entry and recalculate dependent vehicle stats."""
        entry = await self.get_fuel_entry(entry_id, user_id)
        if not entry:
            return None

        vehicle = await self.get_vehicle(entry.vehicle_id, user_id)
        if not vehicle:
            return None

        entry.mileage_km = max(0, mileage_km)
        entry.liters = liters
        entry.total_cost = total_cost
        entry.price_per_liter = total_cost / liters if liters > 0 else None
        entry.is_full_tank = is_full_tank
        entry.station = station

        if mileage_km > vehicle.current_mileage_km:
            vehicle.current_mileage_km = mileage_km
            vehicle.updated_at = datetime.now(timezone.utc)

        await self.db.flush()
        await self._recalculate_vehicle_fuel_stats(user_id, entry.vehicle_id)
        await self.db.refresh(entry)
        return entry

    async def delete_fuel_entry(self, entry_id: int, user_id: int) -> bool:
        """Delete a fuel entry owned by the user and recalculate stats."""
        entry = await self.get_fuel_entry(entry_id, user_id)
        if not entry:
            return False

        vehicle_id = entry.vehicle_id
        await self.db.delete(entry)
        await self.db.flush()
        await self._recalculate_vehicle_fuel_stats(user_id, vehicle_id)
        return True

    async def get_fuel_summary(self, user_id: int, vehicle_id: Optional[int] = None) -> dict:
        """Return aggregate fuel stats."""
        query = select(
            func.count(DriverFuelEntry.id),
            func.sum(DriverFuelEntry.total_cost),
            func.avg(DriverFuelEntry.consumption_l_per_100),
            func.avg(DriverFuelEntry.cost_per_km),
        ).where(DriverFuelEntry.user_id == user_id)
        if vehicle_id is not None:
            query = query.where(DriverFuelEntry.vehicle_id == vehicle_id)

        result = await self.db.execute(query)
        count, total_cost, avg_consumption, avg_cost_per_km = result.one()
        return {
            "count": count or 0,
            "total_cost": float(total_cost or 0),
            "avg_consumption": float(avg_consumption) if avg_consumption is not None else None,
            "avg_cost_per_km": float(avg_cost_per_km) if avg_cost_per_km is not None else None,
        }

    async def mark_service_done(
        self,
        vehicle_id: int,
        user_id: int,
        service_mileage_km: int,
        serviced_at_utc: Optional[datetime] = None,
    ) -> Optional[DriverVehicle]:
        """Mark regular service as completed for a vehicle."""
        vehicle = await self.get_vehicle(vehicle_id, user_id)
        if not vehicle:
            return None

        vehicle.last_service_mileage_km = max(0, service_mileage_km)
        vehicle.last_service_at_utc = serviced_at_utc or datetime.now(timezone.utc)
        if service_mileage_km > vehicle.current_mileage_km:
            vehicle.current_mileage_km = service_mileage_km
        vehicle.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(vehicle)
        return vehicle

    async def get_service_plan(
        self,
        vehicle_id: int,
        user_id: int,
        now_utc: Optional[datetime] = None,
    ) -> Optional[dict]:
        """Return regular service status by mileage and date."""
        vehicle = await self.get_vehicle(vehicle_id, user_id)
        if not vehicle:
            return None

        now_utc = now_utc or datetime.now(timezone.utc)
        next_mileage = None
        remaining_km = None
        mileage_status = "unknown"
        if vehicle.last_service_mileage_km is not None:
            next_mileage = vehicle.last_service_mileage_km + vehicle.service_interval_km
            remaining_km = next_mileage - vehicle.current_mileage_km
            if remaining_km <= 0:
                mileage_status = "overdue"
            elif remaining_km <= max(500, int(vehicle.service_interval_km * 0.1)):
                mileage_status = "soon"
            else:
                mileage_status = "ok"

        next_date = None
        days_left = None
        date_status = "unknown"
        if vehicle.last_service_at_utc is not None:
            last_service = vehicle.last_service_at_utc
            if last_service.tzinfo is None:
                last_service = last_service.replace(tzinfo=timezone.utc)
            next_date = _add_months(last_service, vehicle.service_interval_months)
            days_left = (next_date.date() - now_utc.date()).days
            if days_left <= 0:
                date_status = "overdue"
            elif days_left <= 14:
                date_status = "soon"
            else:
                date_status = "ok"

        return {
            "vehicle": vehicle,
            "next_mileage": next_mileage,
            "remaining_km": remaining_km,
            "mileage_status": mileage_status,
            "next_date": next_date,
            "days_left": days_left,
            "date_status": date_status,
        }

    async def _get_previous_full_fuel_entry(
        self,
        user_id: int,
        vehicle_id: int,
        before_mileage_km: Optional[int] = None,
    ) -> Optional[DriverFuelEntry]:
        """Return the latest previous full-tank entry before the current mileage."""
        conditions = [
            DriverFuelEntry.user_id == user_id,
            DriverFuelEntry.vehicle_id == vehicle_id,
            DriverFuelEntry.is_full_tank.is_(True),
        ]
        if before_mileage_km is not None:
            conditions.append(DriverFuelEntry.mileage_km < before_mileage_km)

        result = await self.db.execute(
            select(DriverFuelEntry)
            .where(*conditions)
            .order_by(DriverFuelEntry.mileage_km.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_interval_fuel_totals(
        self,
        user_id: int,
        vehicle_id: int,
        after_mileage_km: int,
        before_mileage_km: int,
    ) -> tuple[float, float]:
        """Return liters and cost of refuels between two full-tank odometer marks."""
        result = await self.db.execute(
            select(
                func.sum(DriverFuelEntry.liters),
                func.sum(DriverFuelEntry.total_cost),
            ).where(
                DriverFuelEntry.user_id == user_id,
                DriverFuelEntry.vehicle_id == vehicle_id,
                DriverFuelEntry.mileage_km > after_mileage_km,
                DriverFuelEntry.mileage_km < before_mileage_km,
            )
        )
        liters, cost = result.one()
        return float(liters or 0), float(cost or 0)

    async def _recalculate_vehicle_fuel_stats(self, user_id: int, vehicle_id: int) -> None:
        """Recalculate consumption and cost/km after fuel history changes."""
        result = await self.db.execute(
            select(DriverFuelEntry)
            .where(
                DriverFuelEntry.user_id == user_id,
                DriverFuelEntry.vehicle_id == vehicle_id,
            )
            .order_by(DriverFuelEntry.mileage_km.asc(), DriverFuelEntry.id.asc())
        )
        entries = list(result.scalars().all())

        previous_full: Optional[DriverFuelEntry] = None
        interval_liters = 0.0
        interval_cost = 0.0
        for entry in entries:
            entry.consumption_l_per_100 = None
            entry.cost_per_km = None

            if entry.is_full_tank:
                if previous_full and entry.mileage_km > previous_full.mileage_km:
                    distance_km = entry.mileage_km - previous_full.mileage_km
                    total_liters = interval_liters + entry.liters
                    total_cost = interval_cost + entry.total_cost
                    entry.consumption_l_per_100 = total_liters / distance_km * 100
                    entry.cost_per_km = total_cost / distance_km

                previous_full = entry
                interval_liters = 0.0
                interval_cost = 0.0
            elif previous_full:
                interval_liters += entry.liters
                interval_cost += entry.total_cost

        await self.db.flush()


def _add_months(value: datetime, months: int) -> datetime:
    """Add calendar months without external dependencies."""
    month_index = value.month - 1 + max(1, months)
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)
