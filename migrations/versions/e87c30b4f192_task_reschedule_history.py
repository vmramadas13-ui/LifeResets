"""record append-only task deferrals

Revision ID: e87c30b4f192
Revises: 9a42e6b1c8d0
Create Date: 2026-11-13 12:30:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e87c30b4f192"
down_revision: Union[str, Sequence[str], None] = "9a42e6b1c8d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "task_reschedule_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("plan_date", sa.Date(), nullable=False),
        sa.Column("previous_due_date", sa.Date(), nullable=True),
        sa.Column("defer_to", sa.Date(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_task_reschedule_events_task_id",
        "task_reschedule_events",
        ["task_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_task_reschedule_events_task_id", table_name="task_reschedule_events"
    )
    op.drop_table("task_reschedule_events")
