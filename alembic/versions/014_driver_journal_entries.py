"""Add driver journal entries.

Revision ID: 014
Revises: 013
Create Date: 2026-05-27 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create autonomous driver journal table."""
    op.create_table(
        "driver_journal_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("vehicle_id", sa.Integer(), nullable=True),
        sa.Column("checklist_run_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=80), server_default="note", nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="completed", nullable=False),
        sa.Column("happened_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('completed', 'planned', 'canceled', 'note')", name="ck_driver_journal_status"),
        sa.ForeignKeyConstraint(["checklist_run_id"], ["checklist_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vehicle_id"], ["driver_vehicles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("checklist_run_id", name="ux_driver_journal_checklist_run"),
    )
    op.create_index(op.f("ix_driver_journal_entries_checklist_run_id"), "driver_journal_entries", ["checklist_run_id"], unique=False)
    op.create_index(op.f("ix_driver_journal_entries_event_type"), "driver_journal_entries", ["event_type"], unique=False)
    op.create_index(op.f("ix_driver_journal_entries_happened_at_utc"), "driver_journal_entries", ["happened_at_utc"], unique=False)
    op.create_index(op.f("ix_driver_journal_entries_status"), "driver_journal_entries", ["status"], unique=False)
    op.create_index(op.f("ix_driver_journal_entries_user_id"), "driver_journal_entries", ["user_id"], unique=False)
    op.create_index(op.f("ix_driver_journal_entries_vehicle_id"), "driver_journal_entries", ["vehicle_id"], unique=False)
    op.create_index("ix_driver_journal_user_happened", "driver_journal_entries", ["user_id", "happened_at_utc"], unique=False)
    op.create_index("ix_driver_journal_vehicle_happened", "driver_journal_entries", ["vehicle_id", "happened_at_utc"], unique=False)
    op.create_index("ix_driver_journal_user_type", "driver_journal_entries", ["user_id", "event_type"], unique=False)


def downgrade() -> None:
    """Drop autonomous driver journal table."""
    op.drop_index("ix_driver_journal_user_type", table_name="driver_journal_entries")
    op.drop_index("ix_driver_journal_vehicle_happened", table_name="driver_journal_entries")
    op.drop_index("ix_driver_journal_user_happened", table_name="driver_journal_entries")
    op.drop_index(op.f("ix_driver_journal_entries_vehicle_id"), table_name="driver_journal_entries")
    op.drop_index(op.f("ix_driver_journal_entries_user_id"), table_name="driver_journal_entries")
    op.drop_index(op.f("ix_driver_journal_entries_status"), table_name="driver_journal_entries")
    op.drop_index(op.f("ix_driver_journal_entries_happened_at_utc"), table_name="driver_journal_entries")
    op.drop_index(op.f("ix_driver_journal_entries_event_type"), table_name="driver_journal_entries")
    op.drop_index(op.f("ix_driver_journal_entries_checklist_run_id"), table_name="driver_journal_entries")
    op.drop_table("driver_journal_entries")
