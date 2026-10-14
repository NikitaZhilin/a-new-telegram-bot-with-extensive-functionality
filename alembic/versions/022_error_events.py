"""Error journal for the admin panel.

Revision ID: 022
Revises: 021
Create Date: 2026-10-14 18:40:00.000000

Every error logged by the bot, worker or api is stored here, grouped by kind
(same error in the same place increases ``count``), so the admin can review
them later instead of digging through container logs.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "error_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("service", sa.String(length=20), nullable=False),
        sa.Column("section", sa.String(length=40), nullable=False),
        sa.Column("error_type", sa.String(length=120), nullable=False),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("context", sa.String(length=300), nullable=True),
        sa.Column("traceback", sa.Text(), nullable=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fingerprint", name="uq_error_events_fingerprint"),
    )
    op.create_index("ix_error_events_service", "error_events", ["service"])
    op.create_index("ix_error_events_section", "error_events", ["section"])
    op.create_index("ix_error_events_last_seen_at", "error_events", ["last_seen_at"])
    op.create_index("ix_error_events_resolved_at", "error_events", ["resolved_at"])


def downgrade() -> None:
    op.drop_index("ix_error_events_resolved_at", table_name="error_events")
    op.drop_index("ix_error_events_last_seen_at", table_name="error_events")
    op.drop_index("ix_error_events_section", table_name="error_events")
    op.drop_index("ix_error_events_service", table_name="error_events")
    op.drop_table("error_events")
