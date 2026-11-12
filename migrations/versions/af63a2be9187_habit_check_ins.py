"""record habit completion and recovery check-ins

Revision ID: af63a2be9187
Revises: 7d1db751c6a3
Create Date: 2026-11-12 12:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "af63a2be9187"
down_revision: Union[str, Sequence[str], None] = "7d1db751c6a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "habit_check_ins",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("habit_id", sa.Uuid(), nullable=False),
        sa.Column("recorded_on", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('completed','skipped')", name="valid_habit_checkin_status"
        ),
        sa.ForeignKeyConstraint(["habit_id"], ["habits.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_habit_check_ins_habit_id"),
        "habit_check_ins",
        ["habit_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_habit_check_ins_habit_id"), table_name="habit_check_ins")
    op.drop_table("habit_check_ins")
