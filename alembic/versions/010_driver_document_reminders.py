"""Link driver document reminders.

Revision ID: 010
Revises: 009
Create Date: 2026-05-25 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add optional driver document link to reminders."""
    op.add_column("reminders", sa.Column("driver_document_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_reminders_driver_document_id",
        "reminders",
        "driver_documents",
        ["driver_document_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_reminders_driver_document_id"),
        "reminders",
        ["driver_document_id"],
        unique=False,
    )
    op.create_index(
        "ix_reminders_driver_document_status",
        "reminders",
        ["driver_document_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    """Remove optional driver document link from reminders."""
    op.drop_index("ix_reminders_driver_document_status", table_name="reminders")
    op.drop_index(op.f("ix_reminders_driver_document_id"), table_name="reminders")
    op.drop_constraint("fk_reminders_driver_document_id", "reminders", type_="foreignkey")
    op.drop_column("reminders", "driver_document_id")
