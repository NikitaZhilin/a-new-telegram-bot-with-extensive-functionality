"""Add reminder notification delivery plan.

Revision ID: 019
Revises: 018
Create Date: 2026-05-29 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


notification_status = sa.Enum(
    "PENDING",
    "SENT",
    "CANCELED",
    "FAILED",
    name="remindernotificationstatus",
)


def upgrade() -> None:
    """Create notification rows for one reminder event with many deliveries."""
    op.create_table(
        "reminder_notifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("reminder_id", sa.Integer(), nullable=False),
        sa.Column("notify_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("offset_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", notification_status, nullable=False, server_default="PENDING"),
        sa.Column("sent_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("offset_minutes >= 0", name="ck_reminder_notifications_offset_non_negative"),
        sa.ForeignKeyConstraint(["reminder_id"], ["reminders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_reminder_notifications_reminder_id"),
        "reminder_notifications",
        ["reminder_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reminder_notifications_notify_at_utc"),
        "reminder_notifications",
        ["notify_at_utc"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reminder_notifications_status"),
        "reminder_notifications",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_reminder_notifications_status_notify",
        "reminder_notifications",
        ["status", "notify_at_utc"],
        unique=False,
    )
    op.create_index(
        "ix_reminder_notifications_reminder_status",
        "reminder_notifications",
        ["reminder_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_reminder_notifications_reminder_notify",
        "reminder_notifications",
        ["reminder_id", "notify_at_utc"],
        unique=False,
    )

    op.execute(
        """
        INSERT INTO reminder_notifications (
            reminder_id,
            notify_at_utc,
            offset_minutes,
            status,
            sent_at_utc,
            created_at,
            updated_at
        )
        SELECT
            id,
            remind_at_utc,
            0,
            (CASE
                WHEN UPPER(status::text) IN ('CANCELED', 'MISSED') THEN 'CANCELED'
                WHEN notified_at IS NOT NULL OR UPPER(status::text) = 'DONE' THEN 'SENT'
                ELSE 'PENDING'
            END)::remindernotificationstatus,
            notified_at,
            created_at,
            updated_at
        FROM reminders
        WHERE NOT EXISTS (
            SELECT 1
            FROM reminder_notifications rn
            WHERE rn.reminder_id = reminders.id
        )
        """
    )


def downgrade() -> None:
    """Drop reminder delivery plan table."""
    op.drop_index("ix_reminder_notifications_reminder_notify", table_name="reminder_notifications")
    op.drop_index("ix_reminder_notifications_reminder_status", table_name="reminder_notifications")
    op.drop_index("ix_reminder_notifications_status_notify", table_name="reminder_notifications")
    op.drop_index(op.f("ix_reminder_notifications_status"), table_name="reminder_notifications")
    op.drop_index(op.f("ix_reminder_notifications_notify_at_utc"), table_name="reminder_notifications")
    op.drop_index(op.f("ix_reminder_notifications_reminder_id"), table_name="reminder_notifications")
    op.drop_table("reminder_notifications")
    notification_status.drop(op.get_bind(), checkfirst=True)
