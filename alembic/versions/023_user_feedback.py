"""User feedback sent from the bot.

Revision ID: 023
Revises: 022
Create Date: 2026-10-14 18:50:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "023"
down_revision: Union[str, None] = "022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_feedback",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="other"),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("photo_file_id", sa.String(length=255), nullable=True),
        sa.Column("app_version", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="new"),
        sa.Column("admin_reply", sa.Text(), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("kind IN ('bug', 'idea', 'other')", name="ck_user_feedback_kind"),
        sa.CheckConstraint("status IN ('new', 'read', 'answered')", name="ck_user_feedback_status"),
    )
    op.create_index("ix_user_feedback_user_id", "user_feedback", ["user_id"])
    op.create_index("ix_user_feedback_telegram_id", "user_feedback", ["telegram_id"])
    op.create_index("ix_user_feedback_status", "user_feedback", ["status"])
    op.create_index("ix_user_feedback_created_at", "user_feedback", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_user_feedback_created_at", table_name="user_feedback")
    op.drop_index("ix_user_feedback_status", table_name="user_feedback")
    op.drop_index("ix_user_feedback_telegram_id", table_name="user_feedback")
    op.drop_index("ix_user_feedback_user_id", table_name="user_feedback")
    op.drop_table("user_feedback")
