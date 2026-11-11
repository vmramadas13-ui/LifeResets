"""store consent-gated guided Awakening answers

Revision ID: cc4f0e04d4b0
Revises: 5afc2c97f91b
Create Date: 2026-11-12 00:15:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "cc4f0e04d4b0"
down_revision: Union[str, Sequence[str], None] = "5afc2c97f91b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("onboarding_steps", sa.Column("answer", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("onboarding_steps", "answer")
