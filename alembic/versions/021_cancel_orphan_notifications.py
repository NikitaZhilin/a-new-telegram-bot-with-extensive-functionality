"""Close pending deliveries of reminders that are no longer active.

Revision ID: 021
Revises: 020
Create Date: 2026-10-14 12:00:00.000000

Canceling a medication schedule used to change only the reminder status, so
its delivery rows stayed PENDING forever. The worker never sent them (it only
takes active reminders), but they cluttered status checks.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE reminder_notifications
        SET status = 'CANCELED', last_error = 'Reminder is no longer active'
        WHERE status = 'PENDING'
          AND reminder_id IN (SELECT id FROM reminders WHERE status <> 'ACTIVE')
        """
    )


def downgrade() -> None:
    pass
