"""Versioned, reversible activity progression rules."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from liferesets.models import ProgressionEvent, ProgressionSettings, Task

RULESET_VERSION = "starter-1"
XP_PER_TASK = 10
XP_PER_LEVEL = 100
RANK_THRESHOLDS: tuple[tuple[str, int], ...] = (
    ("E", 0),
    ("D", 100),
    ("C", 300),
    ("B", 600),
    ("A", 1000),
    ("S", 1500),
    ("SS", 2200),
    ("SSS", 3000),
)


def progression_paused(db: Session, user_id: UUID) -> bool:
    """Return whether this account has paused new progression awards."""
    settings = db.get(ProgressionSettings, user_id)
    return bool(settings and settings.paused)


def record_task_transition(
    db: Session, task: Task, old_status: str, new_status: str
) -> None:
    """Append an XP award or correction when a task's completion state changes."""
    if old_status == new_status:
        return

    existing_xp = (
        db.scalar(
            select(func.coalesce(func.sum(ProgressionEvent.xp_delta), 0)).where(
                ProgressionEvent.user_id == task.user_id,
                ProgressionEvent.task_id == task.id,
            )
        )
        or 0
    )

    if new_status == "completed" and existing_xp <= 0:
        if progression_paused(db, task.user_id):
            return
        db.add(
            ProgressionEvent(
                user_id=task.user_id,
                task_id=task.id,
                domain=task.domain,
                event_type="task_completed",
                xp_delta=XP_PER_TASK,
                ruleset_version=RULESET_VERSION,
                reason="Task marked complete.",
            )
        )
    elif old_status == "completed" and new_status != "completed" and existing_xp > 0:
        db.add(
            ProgressionEvent(
                user_id=task.user_id,
                task_id=task.id,
                domain=task.domain,
                event_type="task_reopened",
                xp_delta=-min(existing_xp, XP_PER_TASK),
                ruleset_version=RULESET_VERSION,
                reason="Completion was changed; prior XP was corrected.",
            )
        )
