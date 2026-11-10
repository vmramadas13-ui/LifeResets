"""Deterministic, non-persistent planning previews."""

from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from liferesets.database import get_db
from liferesets.models import Goal, Task
from liferesets.security import Authenticated

router = APIRouter(prefix="/api/v1/plans", tags=["planning"])


def make_preview(
    db: Session, user_id: UUID, start: date, days: int
) -> dict[str, object]:
    """Build a small ordered quest preview from the user's own active records."""
    end = start + timedelta(days=days - 1)
    goals = db.scalars(
        select(Goal)
        .where(Goal.user_id == user_id, Goal.status == "active")
        .order_by(Goal.priority.desc(), Goal.target_date, Goal.created_at)
        .limit(8)
    ).all()
    tasks = db.scalars(
        select(Task)
        .where(Task.user_id == user_id, Task.status == "pending")
        .order_by(Task.due_date, Task.created_at)
        .limit(16)
    ).all()
    quests: list[dict[str, object]] = []
    for task in tasks:
        if task.due_date is None or start <= task.due_date <= end:
            quests.append(
                {
                    "kind": "existing_task",
                    "task_id": str(task.id),
                    "goal_id": str(task.goal_id) if task.goal_id else None,
                    "title": task.title,
                    "due_date": task.due_date.isoformat() if task.due_date else None,
                    "reason": "Pending user-created task",
                }
            )
    covered_goals = {quest["goal_id"] for quest in quests}
    for goal in goals:
        if str(goal.id) not in covered_goals and len(quests) < 12:
            quests.append(
                {
                    "kind": "goal_prompt",
                    "goal_id": str(goal.id),
                    "title": f"Choose one next action: {goal.title}",
                    "due_date": None,
                    "reason": "Active goal has no pending task in this preview",
                }
            )
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "quests": quests,
        "is_preview": True,
        "persisted": False,
        "generated_actions": False,
    }


@router.get("/preview")
def planning_preview(
    auth: Authenticated,
    db: Session = Depends(get_db),
    start_date: date = Query(default_factory=date.today),
    days: int = Query(default=7, ge=1, le=31),
) -> dict[str, object]:
    """Return owned tasks and prompts without writing records or dispatching actions."""
    return make_preview(db, auth.user.id, start_date, days)
