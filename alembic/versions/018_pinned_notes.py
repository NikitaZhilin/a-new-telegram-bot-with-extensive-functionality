"""Add pinned flag to notes.

Revision ID: 018
Revises: 017
Create Date: 2026-05-29 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add pinned flag for quick access to important notes."""
    op.add_column(
        "notes",
        sa.Column("is_pinned", sa.Boolean(), server_default="false", nullable=False),
    )
    op.create_index(op.f("ix_notes_is_pinned"), "notes", ["is_pinned"], unique=False)


def downgrade() -> None:
    """Remove pinned flag."""
    op.drop_index(op.f("ix_notes_is_pinned"), table_name="notes")
    op.drop_column("notes", "is_pinned")
