"""Transparent activity-based RPG progression, not a measure of personal worth."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from liferesets.database import get_db
from liferesets.models import Task
from liferesets.security import Authenticated

router = APIRouter(prefix="/api/v1/rpg", tags=["RPG progression"])
XP_PER_COMPLETED_TASK = 10
XP_PER_LEVEL = 100


@router.get("/status")
def rpg_status(auth: Authenticated, db: Session = Depends(get_db)) -> dict[str, object]:
    """Derive a visible activity level from completed tasks owned by this account."""
    completed = (
        db.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.user_id == auth.user.id, Task.status == "completed")
        )
        or 0
    )
    xp = completed * XP_PER_COMPLETED_TASK
    level = xp // XP_PER_LEVEL + 1
    achievements: list[str] = []
    if completed >= 1:
        achievements.append("first_completed_task")
    if completed >= 10:
        achievements.append("ten_completed_tasks")
    return {
        "level": level,
        "total_xp": xp,
        "xp_in_level": xp % XP_PER_LEVEL,
        "xp_to_next_level": XP_PER_LEVEL - xp % XP_PER_LEVEL,
        "completed_tasks": completed,
        "achievements": achievements,
        "rule": (
            f"{XP_PER_COMPLETED_TASK} XP per completed task; "
            f"{XP_PER_LEVEL} XP per level"
        ),
        "meaning": "Activity progress only; this is not a score of personal worth.",
    }
