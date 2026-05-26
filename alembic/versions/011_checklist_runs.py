"""Add interactive checklist runs.

Revision ID: 011
Revises: 010
Create Date: 2026-05-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create tables for personal checklist executions."""
    op.create_table(
        "checklist_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("source_list_id", sa.Integer(), nullable=True),
        sa.Column("title_snapshot", sa.String(length=255), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('active', 'completed', 'canceled')", name="ck_checklist_runs_status"),
        sa.ForeignKeyConstraint(["source_list_id"], ["lists.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_checklist_runs_completed_at"), "checklist_runs", ["completed_at"], unique=False)
    op.create_index("ix_checklist_runs_list_created", "checklist_runs", ["source_list_id", "created_at"], unique=False)
    op.create_index(op.f("ix_checklist_runs_source_list_id"), "checklist_runs", ["source_list_id"], unique=False)
    op.create_index(op.f("ix_checklist_runs_status"), "checklist_runs", ["status"], unique=False)
    op.create_index(op.f("ix_checklist_runs_user_id"), "checklist_runs", ["user_id"], unique=False)
    op.create_index("ix_checklist_runs_user_status", "checklist_runs", ["user_id", "status"], unique=False)

    op.create_table(
        "checklist_run_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("source_item_id", sa.Integer(), nullable=True),
        sa.Column("text_snapshot", sa.String(length=500), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("checked", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["checklist_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_item_id"], ["list_items.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_checklist_run_items_checked"), "checklist_run_items", ["checked"], unique=False)
    op.create_index("ix_checklist_run_items_run_position", "checklist_run_items", ["run_id", "position"], unique=False)
    op.create_index(op.f("ix_checklist_run_items_run_id"), "checklist_run_items", ["run_id"], unique=False)
    op.create_index(op.f("ix_checklist_run_items_source_item_id"), "checklist_run_items", ["source_item_id"], unique=False)


def downgrade() -> None:
    """Drop checklist execution tables."""
    op.drop_index(op.f("ix_checklist_run_items_source_item_id"), table_name="checklist_run_items")
    op.drop_index(op.f("ix_checklist_run_items_run_id"), table_name="checklist_run_items")
    op.drop_index("ix_checklist_run_items_run_position", table_name="checklist_run_items")
    op.drop_index(op.f("ix_checklist_run_items_checked"), table_name="checklist_run_items")
    op.drop_table("checklist_run_items")

    op.drop_index("ix_checklist_runs_user_status", table_name="checklist_runs")
    op.drop_index(op.f("ix_checklist_runs_user_id"), table_name="checklist_runs")
    op.drop_index(op.f("ix_checklist_runs_status"), table_name="checklist_runs")
    op.drop_index(op.f("ix_checklist_runs_source_list_id"), table_name="checklist_runs")
    op.drop_index("ix_checklist_runs_list_created", table_name="checklist_runs")
    op.drop_index(op.f("ix_checklist_runs_completed_at"), table_name="checklist_runs")
    op.drop_table("checklist_runs")
