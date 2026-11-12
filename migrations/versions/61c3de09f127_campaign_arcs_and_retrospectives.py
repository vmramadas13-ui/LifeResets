"""add weekly campaign arcs, checkpoints, changes, and retrospectives

Revision ID: 61c3de09f127
Revises: 42d916f7bca0
Create Date: 2026-11-13 14:00:00
"""

import uuid
from datetime import timedelta
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "61c3de09f127"
down_revision: Union[str, Sequence[str], None] = "42d916f7bca0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "campaign_arcs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("week_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("focus", sa.Text(), nullable=True),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.CheckConstraint("week_number BETWEEN 1 AND 13", name="valid_campaign_week"),
        sa.CheckConstraint(
            "status IN ('planned','active','completed','skipped')",
            name="valid_campaign_arc_status",
        ),
        sa.CheckConstraint("ends_on >= starts_on", name="valid_campaign_arc_dates"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", "week_number", name="unique_campaign_week"),
    )
    op.create_index("ix_campaign_arcs_campaign_id", "campaign_arcs", ["campaign_id"])
    # Existing campaigns receive the same 13-week structure as new ones.
    campaigns = sa.table(
        "campaigns",
        sa.column("id", sa.Uuid()),
        sa.column("starts_on", sa.Date()),
        sa.column("ends_on", sa.Date()),
    )
    arcs = sa.table(
        "campaign_arcs",
        sa.column("id", sa.Uuid()),
        sa.column("campaign_id", sa.Uuid()),
        sa.column("week_number", sa.Integer()),
        sa.column("title", sa.String(length=160)),
        sa.column("focus", sa.Text()),
        sa.column("starts_on", sa.Date()),
        sa.column("ends_on", sa.Date()),
        sa.column("status", sa.String(length=12)),
    )
    connection = op.get_bind()
    for campaign_id, starts_on, ends_on in connection.execute(
        sa.select(campaigns.c.id, campaigns.c.starts_on, campaigns.c.ends_on)
    ):
        weekly_arcs = []
        for week_number in range(1, 14):
            arc_start = starts_on + timedelta(days=(week_number - 1) * 7)
            if arc_start > ends_on:
                break
            weekly_arcs.append(
                {
                    "id": uuid.uuid4(),
                    "campaign_id": campaign_id,
                    "week_number": week_number,
                    "title": f"Week {week_number}",
                    "focus": None,
                    "starts_on": arc_start,
                    "ends_on": min(arc_start + timedelta(days=6), ends_on),
                    "status": "planned",
                }
            )
        if weekly_arcs:
            connection.execute(arcs.insert(), weekly_arcs)
    op.create_table(
        "campaign_checkpoints",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("arc_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending','completed','skipped')",
            name="valid_campaign_checkpoint_status",
        ),
        sa.ForeignKeyConstraint(["arc_id"], ["campaign_arcs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_campaign_checkpoints_arc_id", "campaign_checkpoints", ["arc_id"]
    )
    op.create_table(
        "campaign_scope_changes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("previous_objective", sa.Text(), nullable=False),
        sa.Column("new_objective", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_campaign_scope_changes_campaign_id",
        "campaign_scope_changes",
        ["campaign_id"],
    )
    op.create_table(
        "campaign_retrospectives",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("wins", sa.Text(), nullable=True),
        sa.Column("blockers", sa.Text(), nullable=True),
        sa.Column("learnings", sa.Text(), nullable=True),
        sa.Column("next_focus", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", name="unique_campaign_retrospective"),
    )


def downgrade() -> None:
    op.drop_table("campaign_retrospectives")
    op.drop_index(
        "ix_campaign_scope_changes_campaign_id", table_name="campaign_scope_changes"
    )
    op.drop_table("campaign_scope_changes")
    op.drop_index("ix_campaign_checkpoints_arc_id", table_name="campaign_checkpoints")
    op.drop_table("campaign_checkpoints")
    op.drop_index("ix_campaign_arcs_campaign_id", table_name="campaign_arcs")
    op.drop_table("campaign_arcs")
