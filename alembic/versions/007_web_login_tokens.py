"""Add web login tokens.

Revision ID: 007
Revises: 006
Create Date: 2026-05-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create hashed web access tokens for user-scoped web login."""
    op.create_table(
        "web_login_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("use_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_web_login_tokens_user_id", "web_login_tokens", ["user_id"])
    op.create_index("ix_web_login_tokens_token_hash", "web_login_tokens", ["token_hash"], unique=True)
    op.create_index("ix_web_login_tokens_expires_at_utc", "web_login_tokens", ["expires_at_utc"])
    op.create_index("ix_web_login_tokens_is_active", "web_login_tokens", ["is_active"])
    op.create_index("ix_web_login_tokens_user_active", "web_login_tokens", ["user_id", "is_active"])


def downgrade() -> None:
    """Drop web access tokens."""
    op.drop_index("ix_web_login_tokens_user_active", table_name="web_login_tokens")
    op.drop_index("ix_web_login_tokens_is_active", table_name="web_login_tokens")
    op.drop_index("ix_web_login_tokens_expires_at_utc", table_name="web_login_tokens")
    op.drop_index("ix_web_login_tokens_token_hash", table_name="web_login_tokens")
    op.drop_index("ix_web_login_tokens_user_id", table_name="web_login_tokens")
    op.drop_table("web_login_tokens")
