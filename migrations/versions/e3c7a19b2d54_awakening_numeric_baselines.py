"""store consent-gated numeric Awakening baselines

Revision ID: e3c7a19b2d54
Revises: af63a2be9187
Create Date: 2026-11-12 12:15:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e3c7a19b2d54"
down_revision: Union[str, Sequence[str], None] = "af63a2be9187"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "awakening_baselines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("domain", sa.String(length=32), nullable=False),
        sa.Column("metric_name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("value", sa.Numeric(precision=16, scale=4), nullable=True),
        sa.Column("unit", sa.String(length=40), nullable=True),
        sa.Column("measured_on", sa.Date(), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "domain IN ('career','fitness','finance','discipline','learning',"
            "'mental_wellness','relationships','lifestyle')",
            name="valid_awakening_baseline_domain",
        ),
        sa.CheckConstraint(
            "status IN ('recorded','unknown')",
            name="valid_awakening_baseline_status",
        ),
        sa.CheckConstraint(
            "(status = 'recorded' AND value IS NOT NULL AND unit IS NOT NULL) OR "
            "(status = 'unknown' AND value IS NULL)",
            name="valid_awakening_baseline_value",
        ),
        sa.CheckConstraint(
            "confidence BETWEEN 0 AND 100", name="valid_baseline_confidence"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_awakening_baselines_user_id"),
        "awakening_baselines",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_awakening_baselines_user_id"), table_name="awakening_baselines"
    )
    op.drop_table("awakening_baselines")
