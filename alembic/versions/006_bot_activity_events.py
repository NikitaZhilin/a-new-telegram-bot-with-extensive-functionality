"""Add sanitized bot activity events.

Revision ID: 006
Revises: 005
Create Date: 2026-05-25 01:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create append-only table for privacy-safe interaction analytics."""
    op.create_table(
        "bot_activity_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("source", sa.String(length=30), server_default="telegram", nullable=False),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("event_name", sa.String(length=120), nullable=False),
        sa.Column("domain", sa.String(length=30), server_default="general", nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_bot_activity_events_user_id", "bot_activity_events", ["user_id"])
    op.create_index("ix_bot_activity_events_telegram_id", "bot_activity_events", ["telegram_id"])
    op.create_index("ix_bot_activity_events_event_type", "bot_activity_events", ["event_type"])
    op.create_index("ix_bot_activity_events_event_name", "bot_activity_events", ["event_name"])
    op.create_index("ix_bot_activity_events_domain", "bot_activity_events", ["domain"])
    op.create_index("ix_bot_activity_events_created_at", "bot_activity_events", ["created_at"])
    op.create_index("ix_bot_activity_user_created", "bot_activity_events", ["user_id", "created_at"])
    op.create_index("ix_bot_activity_domain_created", "bot_activity_events", ["domain", "created_at"])
    op.create_index("ix_bot_activity_event_created", "bot_activity_events", ["event_name", "created_at"])


def downgrade() -> None:
    """Drop bot activity events."""
    op.drop_index("ix_bot_activity_event_created", table_name="bot_activity_events")
    op.drop_index("ix_bot_activity_domain_created", table_name="bot_activity_events")
    op.drop_index("ix_bot_activity_user_created", table_name="bot_activity_events")
    op.drop_index("ix_bot_activity_events_created_at", table_name="bot_activity_events")
    op.drop_index("ix_bot_activity_events_domain", table_name="bot_activity_events")
    op.drop_index("ix_bot_activity_events_event_name", table_name="bot_activity_events")
    op.drop_index("ix_bot_activity_events_event_type", table_name="bot_activity_events")
    op.drop_index("ix_bot_activity_events_telegram_id", table_name="bot_activity_events")
    op.drop_index("ix_bot_activity_events_user_id", table_name="bot_activity_events")
    op.drop_table("bot_activity_events")
