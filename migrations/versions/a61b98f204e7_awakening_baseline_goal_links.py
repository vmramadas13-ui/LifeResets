"""link awakening starting points to goals by user choice

Revision ID: a61b98f204e7
Revises: 4e6c9014dfba
Create Date: 2026-11-12 19:10:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a61b98f204e7"
down_revision: Union[str, Sequence[str], None] = "4e6c9014dfba"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "awakening_baseline_goal_links",
        sa.Column("baseline_id", sa.Uuid(), nullable=False),
        sa.Column("goal_id", sa.Uuid(), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["baseline_id"], ["awakening_baselines.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("baseline_id"),
    )
    op.create_index(
        "ix_baseline_goal_links_goal_id",
        "awakening_baseline_goal_links",
        ["goal_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_baseline_goal_links_goal_id", table_name="awakening_baseline_goal_links"
    )
    op.drop_table("awakening_baseline_goal_links")
