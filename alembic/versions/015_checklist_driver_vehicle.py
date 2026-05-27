"""Link checklist runs to driver vehicles.

Revision ID: 015
Revises: 014
Create Date: 2026-05-27 13:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add optional vehicle binding for driver checklist runs."""
    op.add_column("checklist_runs", sa.Column("driver_vehicle_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_checklist_runs_driver_vehicle_id_driver_vehicles",
        "checklist_runs",
        "driver_vehicles",
        ["driver_vehicle_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_checklist_runs_driver_vehicle_id"), "checklist_runs", ["driver_vehicle_id"], unique=False)


def downgrade() -> None:
    """Drop optional vehicle binding for driver checklist runs."""
    op.drop_index(op.f("ix_checklist_runs_driver_vehicle_id"), table_name="checklist_runs")
    op.drop_constraint("fk_checklist_runs_driver_vehicle_id_driver_vehicles", "checklist_runs", type_="foreignkey")
    op.drop_column("checklist_runs", "driver_vehicle_id")
