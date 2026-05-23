"""Add driver assistant schema.

Revision ID: 003
Revises: 002
Create Date: 2026-05-24 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add vehicle profiles and fuel journal entries."""

    op.create_table(
        "driver_vehicles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("make", sa.String(length=120), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("current_mileage_km", sa.Integer(), server_default="0", nullable=False),
        sa.Column("service_interval_km", sa.Integer(), server_default="10000", nullable=False),
        sa.Column("service_interval_months", sa.Integer(), server_default="12", nullable=False),
        sa.Column("last_service_mileage_km", sa.Integer(), nullable=True),
        sa.Column("last_service_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_driver_vehicles_user_id"), "driver_vehicles", ["user_id"], unique=False)
    op.create_index("ix_driver_vehicles_user_created", "driver_vehicles", ["user_id", "created_at"], unique=False)

    op.create_table(
        "driver_fuel_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("vehicle_id", sa.Integer(), nullable=False),
        sa.Column("mileage_km", sa.Integer(), nullable=False),
        sa.Column("liters", sa.Float(), nullable=False),
        sa.Column("total_cost", sa.Float(), nullable=False),
        sa.Column("price_per_liter", sa.Float(), nullable=True),
        sa.Column("is_full_tank", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("station", sa.String(length=255), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("consumption_l_per_100", sa.Float(), nullable=True),
        sa.Column("cost_per_km", sa.Float(), nullable=True),
        sa.Column("filled_at_utc", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vehicle_id"], ["driver_vehicles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_driver_fuel_entries_user_id"), "driver_fuel_entries", ["user_id"], unique=False)
    op.create_index(op.f("ix_driver_fuel_entries_vehicle_id"), "driver_fuel_entries", ["vehicle_id"], unique=False)
    op.create_index(op.f("ix_driver_fuel_entries_mileage_km"), "driver_fuel_entries", ["mileage_km"], unique=False)
    op.create_index(op.f("ix_driver_fuel_entries_is_full_tank"), "driver_fuel_entries", ["is_full_tank"], unique=False)
    op.create_index(op.f("ix_driver_fuel_entries_filled_at_utc"), "driver_fuel_entries", ["filled_at_utc"], unique=False)
    op.create_index("ix_driver_fuel_vehicle_mileage", "driver_fuel_entries", ["vehicle_id", "mileage_km"], unique=False)
    op.create_index("ix_driver_fuel_user_filled", "driver_fuel_entries", ["user_id", "filled_at_utc"], unique=False)


def downgrade() -> None:
    """Remove driver assistant schema."""

    op.drop_index("ix_driver_fuel_user_filled", table_name="driver_fuel_entries")
    op.drop_index("ix_driver_fuel_vehicle_mileage", table_name="driver_fuel_entries")
    op.drop_index(op.f("ix_driver_fuel_entries_filled_at_utc"), table_name="driver_fuel_entries")
    op.drop_index(op.f("ix_driver_fuel_entries_is_full_tank"), table_name="driver_fuel_entries")
    op.drop_index(op.f("ix_driver_fuel_entries_mileage_km"), table_name="driver_fuel_entries")
    op.drop_index(op.f("ix_driver_fuel_entries_vehicle_id"), table_name="driver_fuel_entries")
    op.drop_index(op.f("ix_driver_fuel_entries_user_id"), table_name="driver_fuel_entries")
    op.drop_table("driver_fuel_entries")

    op.drop_index("ix_driver_vehicles_user_created", table_name="driver_vehicles")
    op.drop_index(op.f("ix_driver_vehicles_user_id"), table_name="driver_vehicles")
    op.drop_table("driver_vehicles")
