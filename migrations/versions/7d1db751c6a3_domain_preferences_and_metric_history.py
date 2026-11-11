"""add editable life-area preferences and dated metric history

Revision ID: 7d1db751c6a3
Revises: cc4f0e04d4b0
Create Date: 2026-11-12 01:15:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "7d1db751c6a3"
down_revision: Union[str, Sequence[str], None] = "cc4f0e04d4b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("goal_metrics") as batch_op:
        batch_op.add_column(
            sa.Column("confidence", sa.Integer(), nullable=False, server_default="50")
        )
        batch_op.create_check_constraint(
            "valid_metric_confidence", "confidence BETWEEN 0 AND 100"
        )
        batch_op.alter_column("confidence", server_default=None)

    op.create_table(
        "metric_measurements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("metric_id", sa.Uuid(), nullable=False),
        sa.Column("value", sa.Numeric(precision=16, scale=4), nullable=False),
        sa.Column("recorded_on", sa.Date(), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "confidence BETWEEN 0 AND 100", name="valid_measurement_confidence"
        ),
        sa.CheckConstraint(
            "source IN ('self_report','imported','verified')",
            name="valid_measurement_source",
        ),
        sa.ForeignKeyConstraint(["metric_id"], ["goal_metrics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_metric_measurements_metric_id"),
        "metric_measurements",
        ["metric_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_metric_measurements_metric_id"), table_name="metric_measurements"
    )
    op.drop_table("metric_measurements")
    with op.batch_alter_table("goal_metrics") as batch_op:
        batch_op.drop_constraint("valid_metric_confidence", type_="check")
        batch_op.drop_column("confidence")
