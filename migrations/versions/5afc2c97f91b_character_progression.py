"""versioned character progression and evidence-backed skills

Revision ID: 5afc2c97f91b
Revises: 298a4738d934
Create Date: 2026-11-11 18:00:00
"""

import uuid
from datetime import UTC, datetime
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "5afc2c97f91b"
down_revision: Union[str, Sequence[str], None] = "298a4738d934"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "progression_settings",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("hunter_name", sa.String(length=80), nullable=False),
        sa.Column("callsign", sa.String(length=80), nullable=True),
        sa.Column("paused", sa.Boolean(), nullable=False),
        sa.Column("ruleset_version", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "progression_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("correction_of_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("xp_delta", sa.Integer(), nullable=False),
        sa.Column("ruleset_version", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=240), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('task_completed','task_reopened','correction')",
            name="valid_progression_event_type",
        ),
        sa.CheckConstraint("xp_delta BETWEEN -10000 AND 10000", name="valid_xp_delta"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["correction_of_id"], ["progression_events.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_progression_events_user_id"),
        "progression_events",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_progression_events_task_id"),
        "progression_events",
        ["task_id"],
        unique=False,
    )
    op.create_table(
        "skills",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("domain", sa.String(length=32), nullable=True),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("definition", sa.String(length=500), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "domain IS NULL OR domain IN ('career','fitness','finance','discipline',"
            "'learning','mental_wellness','relationships','lifestyle')",
            name="valid_skill_domain",
        ),
        sa.CheckConstraint("level BETWEEN 1 AND 10", name="valid_skill_level"),
        sa.CheckConstraint(
            "confidence BETWEEN 0 AND 100", name="valid_skill_confidence"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", name="unique_user_skill_name"),
    )
    op.create_index(op.f("ix_skills_user_id"), "skills", ["user_id"], unique=False)
    op.create_table(
        "skill_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("skill_id", sa.Uuid(), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("artifact_ref", sa.String(length=500), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "confidence BETWEEN 0 AND 100", name="valid_skill_evidence_confidence"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_skill_evidence_user_id"), "skill_evidence", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_skill_evidence_skill_id"),
        "skill_evidence",
        ["skill_id"],
        unique=False,
    )
    op.create_table(
        "agent_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("goal_id", sa.Uuid(), nullable=False),
        sa.Column("result_task_id", sa.Uuid(), nullable=True),
        sa.Column("action_type", sa.String(length=40), nullable=False),
        sa.Column("risk_tier", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("proposal", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "risk_tier = 'local_reversible'", name="valid_agent_action_risk_tier"
        ),
        sa.CheckConstraint(
            "status IN ('proposed','approved','rejected','undone')",
            name="valid_agent_action_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["result_task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_agent_actions_user_id"), "agent_actions", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_agent_actions_goal_id"), "agent_actions", ["goal_id"], unique=False
    )

    # Preserve existing task-based XP in the new append-only ledger.
    metadata = sa.MetaData()
    tasks = sa.Table(
        "tasks",
        metadata,
        sa.Column("id", sa.Uuid()),
        sa.Column("user_id", sa.Uuid()),
        sa.Column("status", sa.String(length=16)),
    )
    events = sa.Table(
        "progression_events",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid()),
        sa.Column("task_id", sa.Uuid()),
        sa.Column("correction_of_id", sa.Uuid()),
        sa.Column("event_type", sa.String(length=32)),
        sa.Column("xp_delta", sa.Integer()),
        sa.Column("ruleset_version", sa.String(length=32)),
        sa.Column("reason", sa.String(length=240)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    connection = op.get_bind()
    for task_id, user_id in connection.execute(
        sa.select(tasks.c.id, tasks.c.user_id).where(tasks.c.status == "completed")
    ):
        connection.execute(
            sa.insert(events).values(
                id=uuid.uuid4(),
                user_id=user_id,
                task_id=task_id,
                correction_of_id=None,
                event_type="task_completed",
                xp_delta=10,
                ruleset_version="starter-1",
                reason="Migrated prior task completion.",
                created_at=datetime.now(UTC),
            )
        )


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_actions_goal_id"), table_name="agent_actions")
    op.drop_index(op.f("ix_agent_actions_user_id"), table_name="agent_actions")
    op.drop_table("agent_actions")
    op.drop_index(op.f("ix_skill_evidence_skill_id"), table_name="skill_evidence")
    op.drop_index(op.f("ix_skill_evidence_user_id"), table_name="skill_evidence")
    op.drop_table("skill_evidence")
    op.drop_index(op.f("ix_skills_user_id"), table_name="skills")
    op.drop_table("skills")
    op.drop_index(
        op.f("ix_progression_events_task_id"), table_name="progression_events"
    )
    op.drop_index(
        op.f("ix_progression_events_user_id"), table_name="progression_events"
    )
    op.drop_table("progression_events")
    op.drop_table("progression_settings")
