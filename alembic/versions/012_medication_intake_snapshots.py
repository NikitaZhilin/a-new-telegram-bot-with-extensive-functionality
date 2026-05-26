"""Add medication intake snapshots.

Revision ID: 012
Revises: 011
Create Date: 2026-05-26 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Store medication details as they were when the intake was marked."""
    op.add_column("medication_intakes", sa.Column("scheduled_slot_at_utc", sa.DateTime(timezone=True), nullable=True))
    op.add_column("medication_intakes", sa.Column("medication_name_snapshot", sa.String(length=255), nullable=True))
    op.add_column("medication_intakes", sa.Column("dosage_snapshot", sa.String(length=255), nullable=True))
    op.add_column("medication_intakes", sa.Column("instructions_snapshot", sa.Text(), nullable=True))
    op.add_column("medication_intakes", sa.Column("importance_snapshot", sa.String(length=20), nullable=True))
    op.create_index(op.f("ix_medication_intakes_scheduled_slot_at_utc"), "medication_intakes", ["scheduled_slot_at_utc"], unique=False)
    op.create_index("ix_medication_intakes_med_slot", "medication_intakes", ["medication_id", "scheduled_slot_at_utc"], unique=False)


def downgrade() -> None:
    """Drop medication intake snapshot fields."""
    op.drop_index("ix_medication_intakes_med_slot", table_name="medication_intakes")
    op.drop_index(op.f("ix_medication_intakes_scheduled_slot_at_utc"), table_name="medication_intakes")
    op.drop_column("medication_intakes", "importance_snapshot")
    op.drop_column("medication_intakes", "instructions_snapshot")
    op.drop_column("medication_intakes", "dosage_snapshot")
    op.drop_column("medication_intakes", "medication_name_snapshot")
    op.drop_column("medication_intakes", "scheduled_slot_at_utc")
