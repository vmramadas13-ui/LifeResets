"""Start the application schema migration history."""

from collections.abc import Sequence

revision: str = "c5164ae25a00"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Start migration history; domain tables will be added in later modules."""


def downgrade() -> None:
    """Reverse this baseline migration."""
