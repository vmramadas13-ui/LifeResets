"""A fixed local task tool with an explicit approval and reversal gate."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from liferesets.database import get_db
from liferesets.models import (
    AgentAction,
    AuditEvent,
    DailyPlanItem,
    Goal,
    Task,
)
from liferesets.security import Authenticated, AuthenticatedWithCsrf

router = APIRouter(prefix="/api/v1/agent", tags=["bounded agent"])


class ProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goal_id: UUID


class AgentActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goal_id: UUID
    task_title: str = Field(min_length=1, max_length=160)


def _action_payload(action: AgentAction) -> dict[str, object]:
    return {
        "id": str(action.id),
        "action": action.action_type,
        "risk_tier": action.risk_tier,
        "status": action.status,
        "proposal": action.proposal,
        "result_task_id": str(action.result_task_id) if action.result_task_id else None,
        "requires_explicit_approval": action.status == "proposed",
        "external_access": False,
        "tools_available": ["create_task"] if action.status == "proposed" else [],
        "created_at": action.created_at.isoformat(),
        "approved_at": action.approved_at.isoformat() if action.approved_at else None,
        "undone_at": action.undone_at.isoformat() if action.undone_at else None,
    }


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


@router.post("/actions", status_code=201)
def create_action_proposal(
    request: AgentActionRequest,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Record a task proposal; creating a task still requires a separate approval."""
    goal = db.scalar(
        select(Goal).where(
            Goal.id == request.goal_id,
            Goal.user_id == auth.user.id,
            Goal.status == "active",
        )
    )
    if goal is None:
        raise HTTPException(status_code=404, detail="Active goal not found.")
    action = AgentAction(
        user_id=auth.user.id,
        goal_id=goal.id,
        action_type="create_task",
        risk_tier="local_reversible",
        status="proposed",
        proposal={
            "title": request.task_title.strip(),
            "goal_id": str(goal.id),
            "goal_title": goal.title,
            "rationale": "A local task linked to the active goal you selected.",
        },
    )
    db.add(action)
    db.add(AuditEvent(user_id=auth.user.id, action="agent.action_proposed"))
    db.commit()
    db.refresh(action)
    return _action_payload(action)


@router.get("/actions")
def list_action_proposals(
    auth: Authenticated, db: Session = Depends(get_db)
) -> list[dict[str, object]]:
    actions = db.scalars(
        select(AgentAction)
        .where(AgentAction.user_id == auth.user.id)
        .order_by(AgentAction.created_at.desc(), AgentAction.id.desc())
        .limit(50)
    ).all()
    return [_action_payload(action) for action in actions]


@router.post("/actions/{action_id}/approve")
def approve_action(
    action_id: UUID,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Create the one allowlisted local task only after a fresh approval request."""
    action = db.scalar(
        select(AgentAction).where(
            AgentAction.id == action_id, AgentAction.user_id == auth.user.id
        )
    )
    if action is None:
        raise HTTPException(status_code=404, detail="Proposal not found.")
    if action.status == "approved" and action.result_task_id:
        task = db.scalar(
            select(Task).where(
                Task.id == action.result_task_id, Task.user_id == auth.user.id
            )
        )
        if task is not None:
            return {"action": _action_payload(action), "task": _task_payload(task)}
    if action.status != "proposed":
        raise HTTPException(
            status_code=409, detail="This proposal is no longer pending."
        )
    goal = db.scalar(
        select(Goal).where(
            Goal.id == action.goal_id,
            Goal.user_id == auth.user.id,
            Goal.status == "active",
        )
    )
    if goal is None:
        raise HTTPException(
            status_code=409, detail="The linked goal is no longer active."
        )
    approved_at = datetime.now(UTC)
    claimed = db.execute(
        update(AgentAction)
        .where(
            AgentAction.id == action.id,
            AgentAction.user_id == auth.user.id,
            AgentAction.status == "proposed",
        )
        .values(status="approved", approved_at=approved_at)
    )
    if claimed.rowcount != 1:
        db.rollback()
        refreshed = db.scalar(
            select(AgentAction).where(
                AgentAction.id == action_id, AgentAction.user_id == auth.user.id
            )
        )
        if refreshed and refreshed.status == "approved" and refreshed.result_task_id:
            task = db.scalar(
                select(Task).where(
                    Task.id == refreshed.result_task_id,
                    Task.user_id == auth.user.id,
                )
            )
            if task is not None:
                return {
                    "action": _action_payload(refreshed),
                    "task": _task_payload(task),
                }
        raise HTTPException(
            status_code=409, detail="This proposal is no longer pending."
        )

    title = str(action.proposal["title"])
    task = Task(
        user_id=auth.user.id,
        goal_id=goal.id,
        domain=goal.domain,
        title=title,
    )
    db.add(task)
    db.flush()
    action.result_task_id = task.id
    db.add(AuditEvent(user_id=auth.user.id, action="agent.action_approved"))
    db.commit()
    db.refresh(task)
    return {"action": _action_payload(action), "task": _task_payload(task)}


def _task_payload(task: Task) -> dict[str, object]:
    return {
        "id": str(task.id),
        "title": task.title,
        "goal_id": str(task.goal_id) if task.goal_id else None,
        "domain": task.domain,
        "status": task.status,
    }


@router.post("/actions/{action_id}/reject")
def reject_action(
    action_id: UUID,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    action = db.scalar(
        select(AgentAction).where(
            AgentAction.id == action_id, AgentAction.user_id == auth.user.id
        )
    )
    if action is None:
        raise HTTPException(status_code=404, detail="Proposal not found.")
    if action.status == "rejected":
        return _action_payload(action)
    if action.status != "proposed":
        raise HTTPException(
            status_code=409, detail="This proposal is no longer pending."
        )
    action.status = "rejected"
    db.add(AuditEvent(user_id=auth.user.id, action="agent.action_rejected"))
    db.commit()
    return _action_payload(action)


@router.post("/actions/{action_id}/undo")
def undo_action(
    action_id: UUID,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Reverse an approved task by marking it skipped; preserve its history."""
    action = db.scalar(
        select(AgentAction).where(
            AgentAction.id == action_id, AgentAction.user_id == auth.user.id
        )
    )
    if action is None:
        raise HTTPException(status_code=404, detail="Action not found.")
    if action.status == "undone":
        return _action_payload(action)
    if action.status != "approved" or action.result_task_id is None:
        raise HTTPException(
            status_code=409, detail="Only an approved action can be undone."
        )
    task = db.scalar(
        select(Task).where(
            Task.id == action.result_task_id, Task.user_id == auth.user.id
        )
    )
    if task is None:
        raise HTTPException(status_code=409, detail="The created task is unavailable.")
    if task.status != "pending":
        raise HTTPException(
            status_code=409,
            detail=(
                "This action has changed since approval; review it in your task list."
            ),
        )
    if db.scalar(
        select(DailyPlanItem.id).where(DailyPlanItem.task_id == task.id).limit(1)
    ):
        raise HTTPException(
            status_code=409,
            detail="Remove this action from its daily plans before undoing it.",
        )
    task.status = "skipped"
    action.status = "undone"
    action.undone_at = datetime.now(UTC)
    db.add(AuditEvent(user_id=auth.user.id, action="agent.action_undone"))
    db.commit()
    return _action_payload(action)


def export_agent_actions(db: Session, user_id: UUID) -> list[dict[str, object]]:
    """Export one account's reviewed local agent actions without credentials."""
    actions = db.scalars(
        select(AgentAction)
        .where(AgentAction.user_id == user_id)
        .order_by(AgentAction.created_at, AgentAction.id)
    ).all()
    return [_action_payload(action) for action in actions]
