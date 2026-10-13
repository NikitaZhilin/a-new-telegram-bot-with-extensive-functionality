"""Keep the day of month for monthly reminders.

Revision ID: 020
Revises: 019
Create Date: 2026-10-14 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the anchor day so 30th stays 30th after February."""
    op.add_column("reminders", sa.Column("repeat_day_of_month", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("reminders", "repeat_day_of_month")
