"""Break between medication courses.

Revision ID: 024
Revises: 023
Create Date: 2026-10-16 17:40:00.000000

Some medications are taken in courses (e.g. once every 3-6 months). A paused
medication keeps its history and daily times; reminders are off until
``paused_until`` and come back automatically, with a heads-up a chosen number of days before (3, 7 or 14, or none).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "024"
down_revision: Union[str, None] = "023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("medications", sa.Column("paused_until", sa.Date(), nullable=True))
    op.add_column("medications", sa.Column("paused_schedule", sa.JSON(), nullable=True))
    op.add_column("medications", sa.Column("pause_notice_reminder_id", sa.Integer(), nullable=True))
    op.add_column("medications", sa.Column("pause_notice_days", sa.Integer(), nullable=True))
    op.create_index("ix_medications_paused_until", "medications", ["paused_until"])


def downgrade() -> None:
    op.drop_index("ix_medications_paused_until", table_name="medications")
    op.drop_column("medications", "pause_notice_days")
    op.drop_column("medications", "pause_notice_reminder_id")
    op.drop_column("medications", "paused_schedule")
    op.drop_column("medications", "paused_until")
