"""Add driver expenses and documents.

Revision ID: 008
Revises: 007
Create Date: 2026-05-25 04:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create autonomous driver expense and document tables."""

    op.create_table(
        "driver_expenses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("vehicle_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=80), server_default="other", nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("spent_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_driver_expenses_amount_positive"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vehicle_id"], ["driver_vehicles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_driver_expenses_user_id"), "driver_expenses", ["user_id"], unique=False)
    op.create_index(op.f("ix_driver_expenses_vehicle_id"), "driver_expenses", ["vehicle_id"], unique=False)
    op.create_index(op.f("ix_driver_expenses_spent_at_utc"), "driver_expenses", ["spent_at_utc"], unique=False)
    op.create_index("ix_driver_expenses_user_spent", "driver_expenses", ["user_id", "spent_at_utc"], unique=False)
    op.create_index("ix_driver_expenses_vehicle_spent", "driver_expenses", ["vehicle_id", "spent_at_utc"], unique=False)

    op.create_table(
        "driver_documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("vehicle_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("document_type", sa.String(length=80), server_default="other", nullable=False),
        sa.Column("identifier", sa.String(length=255), nullable=True),
        sa.Column("expires_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("remind_before_days", sa.Integer(), server_default="14", nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("remind_before_days >= 0", name="ck_driver_documents_remind_non_negative"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vehicle_id"], ["driver_vehicles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_driver_documents_user_id"), "driver_documents", ["user_id"], unique=False)
    op.create_index(op.f("ix_driver_documents_vehicle_id"), "driver_documents", ["vehicle_id"], unique=False)
    op.create_index(op.f("ix_driver_documents_expires_at_utc"), "driver_documents", ["expires_at_utc"], unique=False)
    op.create_index(op.f("ix_driver_documents_is_active"), "driver_documents", ["is_active"], unique=False)
    op.create_index("ix_driver_documents_user_expires", "driver_documents", ["user_id", "expires_at_utc"], unique=False)
    op.create_index("ix_driver_documents_vehicle_expires", "driver_documents", ["vehicle_id", "expires_at_utc"], unique=False)


def downgrade() -> None:
    """Remove driver expense and document tables."""

    op.drop_index("ix_driver_documents_vehicle_expires", table_name="driver_documents")
    op.drop_index("ix_driver_documents_user_expires", table_name="driver_documents")
    op.drop_index(op.f("ix_driver_documents_is_active"), table_name="driver_documents")
    op.drop_index(op.f("ix_driver_documents_expires_at_utc"), table_name="driver_documents")
    op.drop_index(op.f("ix_driver_documents_vehicle_id"), table_name="driver_documents")
    op.drop_index(op.f("ix_driver_documents_user_id"), table_name="driver_documents")
    op.drop_table("driver_documents")

    op.drop_index("ix_driver_expenses_vehicle_spent", table_name="driver_expenses")
    op.drop_index("ix_driver_expenses_user_spent", table_name="driver_expenses")
    op.drop_index(op.f("ix_driver_expenses_spent_at_utc"), table_name="driver_expenses")
    op.drop_index(op.f("ix_driver_expenses_vehicle_id"), table_name="driver_expenses")
    op.drop_index(op.f("ix_driver_expenses_user_id"), table_name="driver_expenses")
    op.drop_table("driver_expenses")
