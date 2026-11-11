"""Persistent capacity-aware daily plans with explicit recovery previews."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from liferesets.database import get_db
from liferesets.models import AuditEvent, DailyPlan, DailyPlanItem, Task, User
from liferesets.progression import record_task_transition
from liferesets.security import Authenticated, AuthenticatedWithCsrf

router = APIRouter(prefix="/api/v1/daily-plans", tags=["daily planning"])


class PlannedTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: UUID
    planned_minutes: int = Field(ge=1, le=1440)


class DailyPlanInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capacity_minutes: int = Field(ge=1, le=1440)
    energy: Literal["low", "medium", "high"]
    items: list[PlannedTaskInput] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def enforce_unique_tasks_and_capacity(self) -> DailyPlanInput:
        task_ids = [item.task_id for item in self.items]
        if len(set(task_ids)) != len(task_ids):
            raise ValueError("Each task can appear only once in a daily plan")
        if sum(item.planned_minutes for item in self.items) > self.capacity_minutes:
            raise ValueError("Planned minutes cannot exceed daily capacity")
        return self


class DailyPlanItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["planned", "completed", "deferred", "dropped"]
    defer_to: date | None = None

    @model_validator(mode="after")
    def validate_defer_date(self) -> DailyPlanItemUpdate:
        if self.defer_to is not None and self.status != "deferred":
            raise ValueError("defer_to is valid only when status is deferred")
        return self


def _audit(db: Session, user: User, action: str) -> None:
    db.add(AuditEvent(user_id=user.id, action=action))


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "code": "resource_not_found",
            "message": "The requested resource was not found.",
        },
    )


def _item_payload(item: DailyPlanItem) -> dict[str, object]:
    return {
        "id": str(item.id),
        "task_id": str(item.task_id),
        "title": item.task.title,
        "task_status": item.task.status,
        "due_date": item.task.due_date.isoformat() if item.task.due_date else None,
        "position": item.position,
        "planned_minutes": item.planned_minutes,
        "status": item.status,
        "due_date_at_planning": item.due_date_at_planning.isoformat()
        if item.due_date_at_planning
        else None,
        "deferred_to": item.deferred_to.isoformat() if item.deferred_to else None,
        "completed_at": item.completed_at.isoformat() if item.completed_at else None,
    }


def _plan_payload(plan: DailyPlan) -> dict[str, object]:
    items = sorted(plan.items, key=lambda item: item.position)
    return {
        "id": str(plan.id),
        "plan_date": plan.plan_date.isoformat(),
        "capacity_minutes": plan.capacity_minutes,
        "energy": plan.energy,
        "is_saved": True,
        "planned_minutes": sum(
            item.planned_minutes
            for item in items
            if item.status in {"planned", "completed"}
        ),
        "items": [_item_payload(item) for item in items],
    }


@router.get("/{plan_date}")
def get_daily_plan(
    plan_date: date,
    auth: Authenticated,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    plan = db.scalar(
        select(DailyPlan)
        .where(DailyPlan.user_id == auth.user.id, DailyPlan.plan_date == plan_date)
        .options(selectinload(DailyPlan.items).selectinload(DailyPlanItem.task))
    )
    if plan is None:
        return {
            "id": None,
            "plan_date": plan_date.isoformat(),
            "capacity_minutes": 120,
            "energy": "medium",
            "planned_minutes": 0,
            "items": [],
            "is_saved": False,
        }
    return _plan_payload(plan)


@router.put("/{plan_date}")
def save_daily_plan(
    plan_date: date,
    request: DailyPlanInput,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Save a user-selected task list while preserving item decision history."""
    plan = db.scalar(
        select(DailyPlan)
        .where(DailyPlan.user_id == auth.user.id, DailyPlan.plan_date == plan_date)
        .options(selectinload(DailyPlan.items).selectinload(DailyPlanItem.task))
    )
    if plan is None:
        plan = DailyPlan(
            user_id=auth.user.id,
            plan_date=plan_date,
            capacity_minutes=request.capacity_minutes,
            energy=request.energy,
        )
        db.add(plan)
        db.flush()
    else:
        plan.capacity_minutes = request.capacity_minutes
        plan.energy = request.energy

    task_ids = [item.task_id for item in request.items]
    tasks = (
        db.scalars(
            select(Task).where(Task.user_id == auth.user.id, Task.id.in_(task_ids))
        ).all()
        if task_ids
        else []
    )
    task_by_id = {task.id: task for task in tasks}
    if len(task_by_id) != len(task_ids):
        raise _not_found()

    items_by_task = {item.task_id: item for item in plan.items}
    requested_ids = set(task_ids)
    for item in plan.items:
        if item.status == "completed" and item.task_id not in requested_ids:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "completed_plan_item_locked",
                    "message": "Completed items stay in the plan history.",
                },
            )
        if item.task_id not in requested_ids and item.status == "planned":
            item.status = "dropped"
            item.deferred_to = None

    now = datetime.now(UTC)
    for position, selection in enumerate(request.items):
        task = task_by_id[selection.task_id]
        item = items_by_task.get(selection.task_id)
        if task.status == "skipped":
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "task_not_plannable",
                    "message": "Skipped tasks cannot be added to a daily plan.",
                },
            )
        if item is None:
            item = DailyPlanItem(
                task_id=task.id,
                position=position,
                planned_minutes=selection.planned_minutes,
                due_date_at_planning=task.due_date,
            )
            plan.items.append(item)
        else:
            item.position = position
            if item.status != "completed":
                if task.status == "completed":
                    item.status = "completed"
                    item.completed_at = task.completed_at or now
                else:
                    item.status = "planned"
                    item.deferred_to = None
                    item.completed_at = None
            item.planned_minutes = selection.planned_minutes

    history_position = len(request.items)
    for item in plan.items:
        if item.task_id not in requested_ids:
            item.position = history_position
            history_position += 1

    counted_minutes = sum(
        item.planned_minutes
        for item in plan.items
        if item.status in {"planned", "completed"}
    )
    if counted_minutes > plan.capacity_minutes:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "plan_capacity_exceeded",
                "message": "Planned minutes cannot exceed daily capacity.",
            },
        )

    _audit(db, auth.user, "daily_plan.saved")
    db.commit()
    plan = db.scalar(
        select(DailyPlan)
        .where(DailyPlan.id == plan.id, DailyPlan.user_id == auth.user.id)
        .options(selectinload(DailyPlan.items).selectinload(DailyPlanItem.task))
    )
    assert plan is not None
    return _plan_payload(plan)


@router.patch("/{plan_date}/items/{item_id}")
def update_daily_plan_item(
    plan_date: date,
    item_id: UUID,
    changes: DailyPlanItemUpdate,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    item = db.scalar(
        select(DailyPlanItem)
        .join(DailyPlan, DailyPlan.id == DailyPlanItem.plan_id)
        .join(Task, Task.id == DailyPlanItem.task_id)
        .where(
            DailyPlanItem.id == item_id,
            DailyPlan.user_id == auth.user.id,
            DailyPlan.plan_date == plan_date,
            Task.user_id == auth.user.id,
        )
    )
    if item is None:
        raise _not_found()
    plan = db.scalar(
        select(DailyPlan)
        .where(DailyPlan.id == item.plan_id, DailyPlan.user_id == auth.user.id)
        .options(selectinload(DailyPlan.items))
    )
    if plan is None:
        raise _not_found()
    if item.status == "completed" and changes.status != "completed":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "completed_plan_item_locked",
                "message": "Completed items cannot be reopened.",
            },
        )
    if changes.status == "completed":
        if item.task.status == "skipped":
            raise HTTPException(
                status_code=409, detail="Skipped tasks cannot be completed."
            )
        record_task_transition(db, item.task, item.task.status, "completed")
        item.task.status = "completed"
        item.task.completed_at = item.task.completed_at or datetime.now(UTC)
        item.status = "completed"
        item.completed_at = item.completed_at or item.task.completed_at
        item.deferred_to = None
    elif changes.status == "deferred":
        if item.task.status == "completed":
            raise HTTPException(
                status_code=409, detail="Completed tasks cannot be deferred."
            )
        if changes.defer_to is not None and changes.defer_to <= plan_date:
            raise HTTPException(
                status_code=422, detail="defer_to must be after the plan date."
            )
        item.status = "deferred"
        item.deferred_to = changes.defer_to
        if changes.defer_to is not None:
            item.task.due_date = changes.defer_to
    else:
        if item.task.status == "completed":
            raise HTTPException(
                status_code=409, detail="Completed tasks cannot be reopened."
            )
        if changes.status == "planned" and item.status != "planned":
            planned_minutes = sum(
                plan_item.planned_minutes
                for plan_item in plan.items
                if plan_item.id != item.id
                and plan_item.status in {"planned", "completed"}
            )
            if planned_minutes + item.planned_minutes > plan.capacity_minutes:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "plan_capacity_exceeded",
                        "message": "Planned minutes cannot exceed daily capacity.",
                    },
                )
        item.status = changes.status
        item.deferred_to = None
    _audit(db, auth.user, "daily_plan.item_updated")
    db.commit()
    return _item_payload(item)


@router.get("/{plan_date}/recovery")
def recovery_preview(
    plan_date: date,
    auth: Authenticated,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Suggest unfinished items from earlier plans without carrying them forward."""
    candidates = db.execute(
        select(DailyPlanItem, DailyPlan.plan_date, Task)
        .join(DailyPlan, DailyPlan.id == DailyPlanItem.plan_id)
        .join(Task, Task.id == DailyPlanItem.task_id)
        .where(
            DailyPlan.user_id == auth.user.id,
            Task.user_id == auth.user.id,
            DailyPlan.plan_date < plan_date,
            Task.status == "pending",
            DailyPlanItem.status.in_({"planned", "deferred"}),
            (DailyPlanItem.deferred_to.is_(None))
            | (DailyPlanItem.deferred_to <= plan_date),
            (Task.due_date.is_(None)) | (Task.due_date <= plan_date),
        )
        .order_by(DailyPlan.plan_date.desc(), DailyPlanItem.position)
        .limit(100)
    ).all()
    already_on_date = set(
        db.scalars(
            select(DailyPlanItem.task_id)
            .join(DailyPlan, DailyPlan.id == DailyPlanItem.plan_id)
            .where(
                DailyPlan.user_id == auth.user.id,
                DailyPlan.plan_date == plan_date,
            )
        ).all()
    )
    seen: set[UUID] = set()
    items: list[dict[str, object]] = []
    for item, original_date, task in candidates:
        if task.id in seen or task.id in already_on_date:
            continue
        seen.add(task.id)
        items.append(
            {
                "task_id": str(task.id),
                "title": task.title,
                "original_plan_date": original_date.isoformat(),
                "due_date": task.due_date.isoformat() if task.due_date else None,
                "status": item.status,
                "requires_user_choice": True,
            }
        )
    return {
        "for_date": plan_date.isoformat(),
        "items": items,
        "automatic_carry_forward": False,
        "penalty_for_missed_day": False,
    }


def export_daily_plans(db: Session, user_id: UUID) -> list[dict[str, object]]:
    plans = db.scalars(
        select(DailyPlan)
        .where(DailyPlan.user_id == user_id)
        .options(selectinload(DailyPlan.items).selectinload(DailyPlanItem.task))
        .order_by(DailyPlan.plan_date)
    ).all()
    return [_plan_payload(plan) for plan in plans]
