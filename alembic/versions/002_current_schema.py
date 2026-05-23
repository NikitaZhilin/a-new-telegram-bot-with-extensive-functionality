"""Bring schema in sync with current application models.

Revision ID: 002
Revises: 001
Create Date: 2026-05-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add monetization, sharing, medication, and linked reminder schema."""

    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("users", sa.Column("onboarding_source", sa.String(length=100), nullable=True))
    op.create_index(op.f("ix_users_is_admin"), "users", ["is_admin"], unique=False)

    op.create_table(
        "user_subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("plan_code", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("starts_at_utc", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("expires_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("provider_payment_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_subscriptions_user_id"), "user_subscriptions", ["user_id"], unique=False)
    op.create_index(op.f("ix_user_subscriptions_plan_code"), "user_subscriptions", ["plan_code"], unique=False)
    op.create_index(op.f("ix_user_subscriptions_status"), "user_subscriptions", ["status"], unique=False)
    op.create_index(op.f("ix_user_subscriptions_expires_at_utc"), "user_subscriptions", ["expires_at_utc"], unique=False)
    op.create_index("ix_user_subscriptions_user_status", "user_subscriptions", ["user_id", "status"], unique=False)

    op.create_table(
        "list_share_tokens",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("list_id", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("uses_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("max_uses", sa.Integer(), server_default=sa.text("20"), nullable=False),
        sa.Column("token_type", sa.String(length=20), server_default="copy", nullable=False),
        sa.Column("access_role", sa.String(length=20), server_default="editor", nullable=False),
        sa.Column("expires_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["list_id"], ["lists.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_list_share_tokens_token"), "list_share_tokens", ["token"], unique=True)
    op.create_index(op.f("ix_list_share_tokens_list_id"), "list_share_tokens", ["list_id"], unique=False)
    op.create_index(op.f("ix_list_share_tokens_created_by_user_id"), "list_share_tokens", ["created_by_user_id"], unique=False)
    op.create_index(op.f("ix_list_share_tokens_expires_at_utc"), "list_share_tokens", ["expires_at_utc"], unique=False)
    op.create_index(op.f("ix_list_share_tokens_is_active"), "list_share_tokens", ["is_active"], unique=False)

    op.create_table(
        "list_members",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("list_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), server_default="viewer", nullable=False),
        sa.Column("invited_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["list_id"], ["lists.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_list_members_list_id"), "list_members", ["list_id"], unique=False)
    op.create_index(op.f("ix_list_members_user_id"), "list_members", ["user_id"], unique=False)
    op.create_index("ux_list_members_list_user", "list_members", ["list_id", "user_id"], unique=True)

    op.create_table(
        "medications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("dosage", sa.String(length=255), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("importance", sa.String(length=20), server_default="normal", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_medications_user_id"), "medications", ["user_id"], unique=False)
    op.create_index(op.f("ix_medications_is_active"), "medications", ["is_active"], unique=False)
    op.create_index("ix_medications_user_active", "medications", ["user_id", "is_active"], unique=False)

    medication_status = sa.Enum("TAKEN", "SKIPPED", name="medicationintakestatus")
    medication_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "medication_intakes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("medication_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("taken_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", medication_status, nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["medication_id"], ["medications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_medication_intakes_medication_id"), "medication_intakes", ["medication_id"], unique=False)
    op.create_index(op.f("ix_medication_intakes_user_id"), "medication_intakes", ["user_id"], unique=False)
    op.create_index(op.f("ix_medication_intakes_taken_at_utc"), "medication_intakes", ["taken_at_utc"], unique=False)
    op.create_index(op.f("ix_medication_intakes_status"), "medication_intakes", ["status"], unique=False)
    op.create_index("ix_medication_intakes_user_taken", "medication_intakes", ["user_id", "taken_at_utc"], unique=False)

    op.add_column("reminders", sa.Column("list_id", sa.Integer(), nullable=True))
    op.add_column("reminders", sa.Column("medication_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_reminders_list_id_lists", "reminders", "lists", ["list_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_reminders_medication_id_medications", "reminders", "medications", ["medication_id"], ["id"], ondelete="SET NULL")
    op.create_index(op.f("ix_reminders_list_id"), "reminders", ["list_id"], unique=False)
    op.create_index(op.f("ix_reminders_medication_id"), "reminders", ["medication_id"], unique=False)


def downgrade() -> None:
    """Remove schema added by this revision."""

    op.drop_index(op.f("ix_reminders_medication_id"), table_name="reminders")
    op.drop_index(op.f("ix_reminders_list_id"), table_name="reminders")
    op.drop_constraint("fk_reminders_medication_id_medications", "reminders", type_="foreignkey")
    op.drop_constraint("fk_reminders_list_id_lists", "reminders", type_="foreignkey")
    op.drop_column("reminders", "medication_id")
    op.drop_column("reminders", "list_id")

    op.drop_index("ix_medication_intakes_user_taken", table_name="medication_intakes")
    op.drop_index(op.f("ix_medication_intakes_status"), table_name="medication_intakes")
    op.drop_index(op.f("ix_medication_intakes_taken_at_utc"), table_name="medication_intakes")
    op.drop_index(op.f("ix_medication_intakes_user_id"), table_name="medication_intakes")
    op.drop_index(op.f("ix_medication_intakes_medication_id"), table_name="medication_intakes")
    op.drop_table("medication_intakes")
    sa.Enum("TAKEN", "SKIPPED", name="medicationintakestatus").drop(op.get_bind(), checkfirst=True)

    op.drop_index("ix_medications_user_active", table_name="medications")
    op.drop_index(op.f("ix_medications_is_active"), table_name="medications")
    op.drop_index(op.f("ix_medications_user_id"), table_name="medications")
    op.drop_table("medications")

    op.drop_index("ux_list_members_list_user", table_name="list_members")
    op.drop_index(op.f("ix_list_members_user_id"), table_name="list_members")
    op.drop_index(op.f("ix_list_members_list_id"), table_name="list_members")
    op.drop_table("list_members")

    op.drop_index(op.f("ix_list_share_tokens_is_active"), table_name="list_share_tokens")
    op.drop_index(op.f("ix_list_share_tokens_expires_at_utc"), table_name="list_share_tokens")
    op.drop_index(op.f("ix_list_share_tokens_created_by_user_id"), table_name="list_share_tokens")
    op.drop_index(op.f("ix_list_share_tokens_list_id"), table_name="list_share_tokens")
    op.drop_index(op.f("ix_list_share_tokens_token"), table_name="list_share_tokens")
    op.drop_table("list_share_tokens")

    op.drop_index("ix_user_subscriptions_user_status", table_name="user_subscriptions")
    op.drop_index(op.f("ix_user_subscriptions_expires_at_utc"), table_name="user_subscriptions")
    op.drop_index(op.f("ix_user_subscriptions_status"), table_name="user_subscriptions")
    op.drop_index(op.f("ix_user_subscriptions_plan_code"), table_name="user_subscriptions")
    op.drop_index(op.f("ix_user_subscriptions_user_id"), table_name="user_subscriptions")
    op.drop_table("user_subscriptions")

    op.drop_index(op.f("ix_users_is_admin"), table_name="users")
    op.drop_column("users", "onboarding_source")
    op.drop_column("users", "is_admin")
