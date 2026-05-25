"""Add vehicle preset snapshot fields.

Revision ID: 009
Revises: 008
Create Date: 2026-05-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add optional vehicle specification snapshot columns."""

    op.add_column("driver_vehicles", sa.Column("preset_slug", sa.String(length=120), nullable=True))
    op.add_column("driver_vehicles", sa.Column("body_type", sa.String(length=80), nullable=True))
    op.add_column("driver_vehicles", sa.Column("engine_volume_l", sa.Float(), nullable=True))
    op.add_column("driver_vehicles", sa.Column("engine_power_hp", sa.Integer(), nullable=True))
    op.add_column("driver_vehicles", sa.Column("fuel_type", sa.String(length=40), nullable=True))
    op.add_column("driver_vehicles", sa.Column("transmission", sa.String(length=40), nullable=True))
    op.add_column("driver_vehicles", sa.Column("drive_type", sa.String(length=40), nullable=True))
    op.add_column("driver_vehicles", sa.Column("expected_consumption_city_l_per_100", sa.Float(), nullable=True))
    op.add_column("driver_vehicles", sa.Column("expected_consumption_highway_l_per_100", sa.Float(), nullable=True))
    op.add_column("driver_vehicles", sa.Column("expected_consumption_mixed_l_per_100", sa.Float(), nullable=True))
    op.add_column("driver_vehicles", sa.Column("vehicle_specs_note", sa.Text(), nullable=True))

    op.create_check_constraint(
        "ck_driver_vehicles_engine_volume_positive",
        "driver_vehicles",
        "engine_volume_l IS NULL OR engine_volume_l > 0",
    )
    op.create_check_constraint(
        "ck_driver_vehicles_engine_power_positive",
        "driver_vehicles",
        "engine_power_hp IS NULL OR engine_power_hp > 0",
    )
    op.create_check_constraint(
        "ck_driver_vehicles_consumption_city_positive",
        "driver_vehicles",
        "expected_consumption_city_l_per_100 IS NULL OR expected_consumption_city_l_per_100 > 0",
    )
    op.create_check_constraint(
        "ck_driver_vehicles_consumption_highway_positive",
        "driver_vehicles",
        "expected_consumption_highway_l_per_100 IS NULL OR expected_consumption_highway_l_per_100 > 0",
    )
    op.create_check_constraint(
        "ck_driver_vehicles_consumption_mixed_positive",
        "driver_vehicles",
        "expected_consumption_mixed_l_per_100 IS NULL OR expected_consumption_mixed_l_per_100 > 0",
    )


def downgrade() -> None:
    """Remove optional vehicle specification snapshot columns."""

    op.drop_constraint("ck_driver_vehicles_consumption_mixed_positive", "driver_vehicles", type_="check")
    op.drop_constraint("ck_driver_vehicles_consumption_highway_positive", "driver_vehicles", type_="check")
    op.drop_constraint("ck_driver_vehicles_consumption_city_positive", "driver_vehicles", type_="check")
    op.drop_constraint("ck_driver_vehicles_engine_power_positive", "driver_vehicles", type_="check")
    op.drop_constraint("ck_driver_vehicles_engine_volume_positive", "driver_vehicles", type_="check")

    op.drop_column("driver_vehicles", "vehicle_specs_note")
    op.drop_column("driver_vehicles", "expected_consumption_mixed_l_per_100")
    op.drop_column("driver_vehicles", "expected_consumption_highway_l_per_100")
    op.drop_column("driver_vehicles", "expected_consumption_city_l_per_100")
    op.drop_column("driver_vehicles", "drive_type")
    op.drop_column("driver_vehicles", "transmission")
    op.drop_column("driver_vehicles", "fuel_type")
    op.drop_column("driver_vehicles", "engine_power_hp")
    op.drop_column("driver_vehicles", "engine_volume_l")
    op.drop_column("driver_vehicles", "body_type")
    op.drop_column("driver_vehicles", "preset_slug")

