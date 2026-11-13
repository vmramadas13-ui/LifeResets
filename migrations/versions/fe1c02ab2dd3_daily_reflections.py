"""add consent-gated daily reflections

Revision ID: fe1c02ab2dd3
Revises: 61c3de09f127
Create Date: 2026-11-13 15:30:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "fe1c02ab2dd3"
down_revision: Union[str, Sequence[str], None] = "61c3de09f127"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "daily_reflections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("reflection_date", sa.Date(), nullable=False),
        sa.Column("responses", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "reflection_date", name="unique_user_daily_reflection"
        ),
    )
    op.create_index("ix_daily_reflections_user_id", "daily_reflections", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_daily_reflections_user_id", table_name="daily_reflections")
    op.drop_table("daily_reflections")
