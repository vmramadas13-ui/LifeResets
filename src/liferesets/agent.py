"""Proposal-only bounded agent surface; it has no tool or write capability."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from liferesets.database import get_db
from liferesets.models import Goal
from liferesets.security import AuthenticatedWithCsrf

router = APIRouter(prefix="/api/v1/agent", tags=["bounded agent"])


class ProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goal_id: UUID


@router.post("/proposals/next-task")
def propose_next_task(
    request: ProposalRequest,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Return one small task proposal for an owned active goal without writing it."""
    goal = db.scalar(
        select(Goal).where(
            Goal.id == request.goal_id,
            Goal.user_id == auth.user.id,
            Goal.status == "active",
        )
    )
    if goal is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "resource_not_found",
                "message": "The requested resource was not found.",
            },
        )
    return {
        "proposal": {
            "action": "create_task",
            "title": f"Choose one next action for: {goal.title}",
            "goal_id": str(goal.id),
        },
        "scope": "one task linked to this active goal",
        "requires_explicit_approval": True,
        "approval_endpoint": None,
        "execution_available": False,
        "writes_performed": False,
        "external_access": False,
        "tools_available": [],
        "reason": "A proposal only; review and add the task yourself if useful.",
    }
