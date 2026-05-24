"""Add domain source markers for lists and reminders.

Revision ID: 005
Revises: 004
Create Date: 2026-05-24 16:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Mark records by owning bot domain so generic screens stay clean."""
    op.add_column(
        "lists",
        sa.Column("source_module", sa.String(length=30), server_default="general", nullable=False),
    )
    op.add_column(
        "reminders",
        sa.Column("source_module", sa.String(length=30), server_default="general", nullable=False),
    )
    op.create_index("ix_lists_source_module", "lists", ["source_module"])
    op.create_index("ix_reminders_source_module", "reminders", ["source_module"])
    op.create_index(
        "ix_reminders_user_source_status",
        "reminders",
        ["user_id", "source_module", "status"],
    )

    op.execute(
        """
        UPDATE lists
        SET source_module = 'driver'
        WHERE title IN (
            '🚗 Запчасти к покупке',
            '🚗 Проверка перед поездкой',
            '💧 Проверка жидкостей'
        )
        """
    )
    op.execute(
        """
        UPDATE reminders
        SET source_module = 'medication'
        WHERE medication_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE reminders
        SET source_module = 'list'
        WHERE list_id IS NOT NULL
          AND source_module = 'general'
        """
    )
    op.execute(
        """
        UPDATE reminders
        SET source_module = 'driver'
        WHERE text IN (
            'Заменить моторное масло и масляный фильтр',
            'Проверить уровни жидкостей: масло, антифриз, тормозная, омывайка',
            'Помыть кузов и убрать салон',
            'Проверить давление в шинах',
            'Запланировать прохождение ТО'
        )
        """
    )


def downgrade() -> None:
    """Remove domain source markers."""
    op.drop_index("ix_reminders_user_source_status", table_name="reminders")
    op.drop_index("ix_reminders_source_module", table_name="reminders")
    op.drop_index("ix_lists_source_module", table_name="lists")
    op.drop_column("reminders", "source_module")
    op.drop_column("lists", "source_module")
