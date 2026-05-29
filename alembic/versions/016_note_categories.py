"""Add categories to notes.

Revision ID: 016
Revises: 015
Create Date: 2026-05-29 12:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add a lightweight category field for standalone notes."""
    op.add_column(
        "notes",
        sa.Column("category", sa.String(length=40), server_default="other", nullable=False),
    )
    op.create_index(op.f("ix_notes_category"), "notes", ["category"], unique=False)


def downgrade() -> None:
    """Drop note category field."""
    op.drop_index(op.f("ix_notes_category"), table_name="notes")
    op.drop_column("notes", "category")
