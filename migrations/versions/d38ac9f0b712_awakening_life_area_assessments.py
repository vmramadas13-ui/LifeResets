"""store editable Awakening reflections per life area

Revision ID: d38ac9f0b712
Revises: a61b98f204e7
Create Date: 2026-11-12 20:15:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d38ac9f0b712"
down_revision: Union[str, Sequence[str], None] = "a61b98f204e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "awakening_assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("domain", sa.String(length=32), nullable=False),
        sa.Column("current_reality", sa.Text(), nullable=True),
        sa.Column("desired_direction", sa.Text(), nullable=True),
        sa.Column("experiment", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "domain IN ('career','fitness','finance','discipline','learning',"
            "'mental_wellness','relationships','lifestyle')",
            name="valid_awakening_assessment_domain",
        ),
        sa.CheckConstraint(
            "length(trim(coalesce(current_reality, ''))) > 0 OR "
            "length(trim(coalesce(desired_direction, ''))) > 0 OR "
            "length(trim(coalesce(experiment, ''))) > 0",
            name="nonempty_awakening_assessment",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "domain", name="unique_user_assessment_domain"),
    )
    op.create_index(
        "ix_awakening_assessments_user_id",
        "awakening_assessments",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_awakening_assessments_user_id", table_name="awakening_assessments"
    )
    op.drop_table("awakening_assessments")
