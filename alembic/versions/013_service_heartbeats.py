"""Add service heartbeats.

Revision ID: 013
Revises: 012
Create Date: 2026-05-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create runtime heartbeat table for external status probes."""
    op.create_table(
        "service_heartbeats",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("service_name", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="ok", nullable=False),
        sa.Column("version", sa.String(length=80), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("uptime_seconds", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('ok', 'degraded', 'down')", name="ck_service_heartbeats_status"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("service_name"),
    )
    op.create_index(op.f("ix_service_heartbeats_last_seen_at"), "service_heartbeats", ["last_seen_at"], unique=False)
    op.create_index(op.f("ix_service_heartbeats_service_name"), "service_heartbeats", ["service_name"], unique=False)
    op.create_index("ix_service_heartbeats_service_seen", "service_heartbeats", ["service_name", "last_seen_at"], unique=False)
    op.create_index(op.f("ix_service_heartbeats_status"), "service_heartbeats", ["status"], unique=False)


def downgrade() -> None:
    """Drop runtime heartbeat table."""
    op.drop_index(op.f("ix_service_heartbeats_status"), table_name="service_heartbeats")
    op.drop_index("ix_service_heartbeats_service_seen", table_name="service_heartbeats")
    op.drop_index(op.f("ix_service_heartbeats_service_name"), table_name="service_heartbeats")
    op.drop_index(op.f("ix_service_heartbeats_last_seen_at"), table_name="service_heartbeats")
    op.drop_table("service_heartbeats")
