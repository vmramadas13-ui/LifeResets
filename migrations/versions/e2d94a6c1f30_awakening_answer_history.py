"""keep consent-gated history when awakening answers change

Revision ID: e2d94a6c1f30
Revises: b6d28a4c9f10
Create Date: 2026-11-13 00:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e2d94a6c1f30"
down_revision: Union[str, Sequence[str], None] = "b6d28a4c9f10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "awakening_answer_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("step_id", sa.Uuid(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["step_id"], ["onboarding_steps.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_awakening_answer_revisions_step_id"),
        "awakening_answer_revisions",
        ["step_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_awakening_answer_revisions_step_id"),
        table_name="awakening_answer_revisions",
    )
    op.drop_table("awakening_answer_revisions")
