"""add private busy windows and planning hours to daily plans

Revision ID: 9a42e6b1c8d0
Revises: c7f1d6b9a240
Create Date: 2026-11-13 12:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "9a42e6b1c8d0"
down_revision: Union[str, Sequence[str], None] = "c7f1d6b9a240"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "daily_plans",
        sa.Column(
            "day_start_time",
            sa.Time(),
            server_default=sa.text("'09:00:00'"),
            nullable=False,
        ),
    )
    op.add_column(
        "daily_plans",
        sa.Column(
            "day_end_time",
            sa.Time(),
            server_default=sa.text("'21:00:00'"),
            nullable=False,
        ),
    )
    op.create_table(
        "daily_plan_busy_windows",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.CheckConstraint("start_time < end_time", name="valid_busy_window_range"),
        sa.ForeignKeyConstraint(["plan_id"], ["daily_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "position", name="unique_plan_busy_position"),
    )
    op.create_index(
        "ix_daily_plan_busy_windows_plan_id",
        "daily_plan_busy_windows",
        ["plan_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_daily_plan_busy_windows_plan_id", table_name="daily_plan_busy_windows"
    )
    op.drop_table("daily_plan_busy_windows")
    op.drop_column("daily_plans", "day_end_time")
    op.drop_column("daily_plans", "day_start_time")
