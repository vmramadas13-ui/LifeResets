"""snapshot life domains on actions and progression entries

Revision ID: b6d28a4c9f10
Revises: fe1c02ab2dd3
Create Date: 2026-11-13 16:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b6d28a4c9f10"
down_revision: Union[str, Sequence[str], None] = "fe1c02ab2dd3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DOMAIN_CHECK = (
    "domain IN ('career','fitness','finance','discipline','learning',"
    "'mental_wellness','relationships','lifestyle')"
)


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column(
            "domain", sa.String(length=32), server_default="discipline", nullable=False
        ),
    )
    op.execute(
        "UPDATE tasks SET domain = (SELECT goals.domain FROM goals "
        "WHERE goals.id = tasks.goal_id) WHERE goal_id IS NOT NULL "
        "AND EXISTS (SELECT 1 FROM goals WHERE goals.id = tasks.goal_id)"
    )
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.create_check_constraint("valid_task_domain", DOMAIN_CHECK)

    op.add_column(
        "progression_events",
        sa.Column(
            "domain", sa.String(length=32), server_default="discipline", nullable=False
        ),
    )
    op.execute(
        "UPDATE progression_events SET domain = (SELECT tasks.domain FROM tasks "
        "WHERE tasks.id = progression_events.task_id) WHERE task_id IS NOT NULL "
        "AND EXISTS (SELECT 1 FROM tasks WHERE tasks.id = progression_events.task_id)"
    )
    with op.batch_alter_table("progression_events") as batch_op:
        batch_op.create_check_constraint("valid_progression_event_domain", DOMAIN_CHECK)


def downgrade() -> None:
    with op.batch_alter_table("progression_events") as batch_op:
        batch_op.drop_constraint("valid_progression_event_domain", type_="check")
        batch_op.drop_column("domain")
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_constraint("valid_task_domain", type_="check")
        batch_op.drop_column("domain")
