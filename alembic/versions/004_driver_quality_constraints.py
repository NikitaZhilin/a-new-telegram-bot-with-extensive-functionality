"""Add driver mileage baseline and data quality constraints.

Revision ID: 004
Revises: 003
Create Date: 2026-05-24 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add manual mileage baseline and CHECK constraints for driver tables."""
    op.add_column(
        "driver_vehicles",
        sa.Column("manual_mileage_km", sa.Integer(), server_default="0", nullable=False),
    )
    op.execute(
        """
        UPDATE driver_vehicles
        SET
            manual_mileage_km = GREATEST(COALESCE(current_mileage_km, 0), 0),
            current_mileage_km = GREATEST(COALESCE(current_mileage_km, 0), 0),
            service_interval_km = GREATEST(COALESCE(service_interval_km, 10000), 1),
            service_interval_months = GREATEST(COALESCE(service_interval_months, 12), 1),
            last_service_mileage_km = CASE
                WHEN last_service_mileage_km IS NULL THEN NULL
                ELSE GREATEST(last_service_mileage_km, 0)
            END
        """
    )
    op.execute(
        """
        UPDATE driver_fuel_entries
        SET
            mileage_km = GREATEST(COALESCE(mileage_km, 0), 0),
            liters = CASE WHEN liters <= 0 THEN 0.01 ELSE liters END,
            total_cost = CASE WHEN total_cost <= 0 THEN 0.01 ELSE total_cost END,
            price_per_liter = CASE
                WHEN liters > 0 AND total_cost > 0 THEN total_cost / liters
                ELSE NULL
            END,
            consumption_l_per_100 = CASE
                WHEN consumption_l_per_100 IS NULL THEN NULL
                ELSE GREATEST(consumption_l_per_100, 0)
            END,
            cost_per_km = CASE
                WHEN cost_per_km IS NULL THEN NULL
                ELSE GREATEST(cost_per_km, 0)
            END
        """
    )

    op.create_check_constraint(
        "ck_driver_vehicles_manual_mileage_non_negative",
        "driver_vehicles",
        "manual_mileage_km >= 0",
    )
    op.create_check_constraint(
        "ck_driver_vehicles_current_mileage_non_negative",
        "driver_vehicles",
        "current_mileage_km >= 0",
    )
    op.create_check_constraint(
        "ck_driver_vehicles_service_interval_km_positive",
        "driver_vehicles",
        "service_interval_km > 0",
    )
    op.create_check_constraint(
        "ck_driver_vehicles_service_interval_months_positive",
        "driver_vehicles",
        "service_interval_months > 0",
    )
    op.create_check_constraint(
        "ck_driver_vehicles_year_reasonable",
        "driver_vehicles",
        "year IS NULL OR (year >= 1886 AND year <= 2100)",
    )
    op.create_check_constraint(
        "ck_driver_vehicles_last_service_mileage_non_negative",
        "driver_vehicles",
        "last_service_mileage_km IS NULL OR last_service_mileage_km >= 0",
    )
    op.create_check_constraint(
        "ck_driver_fuel_entries_mileage_non_negative",
        "driver_fuel_entries",
        "mileage_km >= 0",
    )
    op.create_check_constraint(
        "ck_driver_fuel_entries_liters_positive",
        "driver_fuel_entries",
        "liters > 0",
    )
    op.create_check_constraint(
        "ck_driver_fuel_entries_total_cost_positive",
        "driver_fuel_entries",
        "total_cost > 0",
    )
    op.create_check_constraint(
        "ck_driver_fuel_entries_price_positive",
        "driver_fuel_entries",
        "price_per_liter IS NULL OR price_per_liter > 0",
    )
    op.create_check_constraint(
        "ck_driver_fuel_entries_consumption_non_negative",
        "driver_fuel_entries",
        "consumption_l_per_100 IS NULL OR consumption_l_per_100 >= 0",
    )
    op.create_check_constraint(
        "ck_driver_fuel_entries_cost_per_km_non_negative",
        "driver_fuel_entries",
        "cost_per_km IS NULL OR cost_per_km >= 0",
    )


def downgrade() -> None:
    """Remove driver CHECK constraints and manual mileage baseline."""
    op.drop_constraint("ck_driver_fuel_entries_cost_per_km_non_negative", "driver_fuel_entries", type_="check")
    op.drop_constraint("ck_driver_fuel_entries_consumption_non_negative", "driver_fuel_entries", type_="check")
    op.drop_constraint("ck_driver_fuel_entries_price_positive", "driver_fuel_entries", type_="check")
    op.drop_constraint("ck_driver_fuel_entries_total_cost_positive", "driver_fuel_entries", type_="check")
    op.drop_constraint("ck_driver_fuel_entries_liters_positive", "driver_fuel_entries", type_="check")
    op.drop_constraint("ck_driver_fuel_entries_mileage_non_negative", "driver_fuel_entries", type_="check")
    op.drop_constraint("ck_driver_vehicles_last_service_mileage_non_negative", "driver_vehicles", type_="check")
    op.drop_constraint("ck_driver_vehicles_year_reasonable", "driver_vehicles", type_="check")
    op.drop_constraint("ck_driver_vehicles_service_interval_months_positive", "driver_vehicles", type_="check")
    op.drop_constraint("ck_driver_vehicles_service_interval_km_positive", "driver_vehicles", type_="check")
    op.drop_constraint("ck_driver_vehicles_current_mileage_non_negative", "driver_vehicles", type_="check")
    op.drop_constraint("ck_driver_vehicles_manual_mileage_non_negative", "driver_vehicles", type_="check")
    op.drop_column("driver_vehicles", "manual_mileage_km")
