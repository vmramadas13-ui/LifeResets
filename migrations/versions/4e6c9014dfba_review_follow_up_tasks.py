"""link one optional task to a completed review

Revision ID: 4e6c9014dfba
Revises: b527d913a064
Create Date: 2026-11-12 18:15:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "4e6c9014dfba"
down_revision: Union[str, Sequence[str], None] = "b527d913a064"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "review_follow_ups",
        sa.Column("review_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["review_id"], ["reviews.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("review_id"),
        sa.UniqueConstraint("task_id", name="uq_review_follow_ups_task"),
    )


def downgrade() -> None:
    op.drop_table("review_follow_ups")
