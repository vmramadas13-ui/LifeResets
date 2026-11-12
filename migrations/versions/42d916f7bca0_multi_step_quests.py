"""add account-owned quests with ordered task steps

Revision ID: 42d916f7bca0
Revises: e87c30b4f192
Create Date: 2026-11-13 13:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "42d916f7bca0"
down_revision: Union[str, Sequence[str], None] = "e87c30b4f192"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "quests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("goal_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active','archived')", name="valid_quest_status"
        ),
        sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quests_user_id", "quests", ["user_id"], unique=False)
    op.create_index("ix_quests_goal_id", "quests", ["goal_id"], unique=False)
    op.create_table(
        "quest_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("quest_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("position >= 0", name="valid_quest_step_position"),
        sa.ForeignKeyConstraint(["quest_id"], ["quests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("quest_id", "position", name="unique_quest_step_position"),
        sa.UniqueConstraint("task_id", name="unique_quest_step_task"),
    )
    op.create_index(
        "ix_quest_steps_quest_id", "quest_steps", ["quest_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_quest_steps_quest_id", table_name="quest_steps")
    op.drop_table("quest_steps")
    op.drop_index("ix_quests_goal_id", table_name="quests")
    op.drop_index("ix_quests_user_id", table_name="quests")
    op.drop_table("quests")
