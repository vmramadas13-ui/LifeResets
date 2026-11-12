"""add user-defined life-area subareas

Revision ID: c7f1d6b9a240
Revises: d38ac9f0b712
Create Date: 2026-11-12 21:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c7f1d6b9a240"
down_revision: Union[str, Sequence[str], None] = "d38ac9f0b712"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "domain_subareas",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("domain", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.CheckConstraint(
            "domain IN ('career','fitness','finance','discipline','learning',"
            "'mental_wellness','relationships','lifestyle')",
            name="valid_subarea_domain",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "domain", "name", name="unique_user_subarea"),
    )
    op.create_index(
        "ix_domain_subareas_user_id", "domain_subareas", ["user_id"], unique=False
    )
    with op.batch_alter_table("goals") as batch_op:
        batch_op.add_column(sa.Column("subarea_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_goals_subarea_id_domain_subareas",
            "domain_subareas",
            ["subarea_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_goals_subarea_id", ["subarea_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("goals") as batch_op:
        batch_op.drop_index("ix_goals_subarea_id")
        batch_op.drop_constraint(
            "fk_goals_subarea_id_domain_subareas", type_="foreignkey"
        )
        batch_op.drop_column("subarea_id")
    op.drop_index("ix_domain_subareas_user_id", table_name="domain_subareas")
    op.drop_table("domain_subareas")
