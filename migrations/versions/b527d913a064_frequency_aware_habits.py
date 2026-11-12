"""add recurrence windows and reminder choices to habits

Revision ID: b527d913a064
Revises: e3c7a19b2d54
Create Date: 2026-11-12 13:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b527d913a064"
down_revision: Union[str, Sequence[str], None] = "e3c7a19b2d54"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("habits") as batch_op:
        batch_op.add_column(
            sa.Column(
                "weekdays",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )
        batch_op.add_column(sa.Column("interval_days", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("start_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("end_date", sa.Date(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "reminder_preference",
                sa.String(length=16),
                nullable=False,
                server_default="none",
            )
        )
        batch_op.create_check_constraint(
            "valid_habit_interval_days",
            "interval_days IS NULL OR interval_days BETWEEN 1 AND 365",
        )
        batch_op.create_check_constraint(
            "valid_habit_date_range",
            "start_date IS NULL OR end_date IS NULL OR end_date >= start_date",
        )
        batch_op.create_check_constraint(
            "valid_habit_reminder_preference",
            "reminder_preference IN ('none','in_app')",
        )


def downgrade() -> None:
    with op.batch_alter_table("habits") as batch_op:
        batch_op.drop_constraint("valid_habit_reminder_preference", type_="check")
        batch_op.drop_constraint("valid_habit_date_range", type_="check")
        batch_op.drop_constraint("valid_habit_interval_days", type_="check")
        batch_op.drop_column("reminder_preference")
        batch_op.drop_column("end_date")
        batch_op.drop_column("start_date")
        batch_op.drop_column("interval_days")
        batch_op.drop_column("weekdays")
