"""Add note links to reminders.

Revision ID: 017
Revises: 016
Create Date: 2026-05-29 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("reminders", sa.Column("note_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_reminders_note_id_notes",
        "reminders",
        "notes",
        ["note_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_reminders_note_id", "reminders", ["note_id"])
    op.create_index("ix_reminders_note_status", "reminders", ["note_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_reminders_note_status", table_name="reminders")
    op.drop_index("ix_reminders_note_id", table_name="reminders")
    op.drop_constraint("fk_reminders_note_id_notes", "reminders", type_="foreignkey")
    op.drop_column("reminders", "note_id")
