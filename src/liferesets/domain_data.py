"""Account-scoped goal, task, habit, and evidence endpoints."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from liferesets.database import get_db
from liferesets.models import AuditEvent, Evidence, Goal, GoalMetric, Habit, Task, User
from liferesets.progression import record_task_transition
from liferesets.security import Authenticated, AuthenticatedWithCsrf

router = APIRouter(prefix="/api/v1", tags=["goals and evidence"])

DomainCode = Literal[
    "career",
    "fitness",
    "finance",
    "discipline",
    "learning",
    "mental_wellness",
    "relationships",
    "lifestyle",
]
GoalStatus = Literal["active", "paused", "completed", "archived"]
TaskStatus = Literal["pending", "completed", "skipped"]

DOMAINS: tuple[dict[str, str], ...] = (
    {
        "code": "career",
        "name": "Career",
        "description": "Work, skills, and opportunities.",
    },
    {
        "code": "fitness",
        "name": "Fitness",
        "description": "Training, nutrition, and recovery.",
    },
    {
        "code": "finance",
        "name": "Finance",
        "description": "Budget, debt, savings, and net worth.",
    },
    {
        "code": "discipline",
        "name": "Discipline",
        "description": "Habits, routines, and focus.",
    },
    {
        "code": "learning",
        "name": "Learning",
        "description": "Study, practice, and demonstrable skills.",
    },
    {
        "code": "mental_wellness",
        "name": "Mental wellness",
        "description": "Self-reported mood, energy, and rest.",
    },
    {
        "code": "relationships",
        "name": "Relationships",
        "description": "User-created plans and reflections.",
    },
    {
        "code": "lifestyle",
        "name": "Lifestyle and adventure",
        "description": "Experiences, hobbies, and milestones.",
    },
)


class MetricInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    unit: str = Field(min_length=1, max_length=40)
    baseline_value: Decimal | None = Field(
        default=None, max_digits=16, decimal_places=4, allow_inf_nan=False
    )
    target_value: Decimal = Field(max_digits=16, decimal_places=4, allow_inf_nan=False)
    current_value: Decimal | None = Field(
        default=None, max_digits=16, decimal_places=4, allow_inf_nan=False
    )
    target_date: date | None = None


class GoalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: DomainCode
    title: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=5000)
    priority: int = Field(default=3, ge=1, le=5)
    target_date: date | None = None
    metrics: list[MetricInput] = Field(default_factory=list, max_length=12)


class GoalUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=5000)
    priority: int | None = Field(default=None, ge=1, le=5)
    status: GoalStatus | None = None
    target_date: date | None = None

    @field_validator("title", "priority", "status", mode="before")
    @classmethod
    def reject_null_required_fields(cls, value: object) -> object:
        if value is None:
            raise ValueError("This field cannot be null")
        return value


class MetricUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline_value: Decimal | None = Field(
        default=None, max_digits=16, decimal_places=4, allow_inf_nan=False
    )
    target_value: Decimal | None = Field(
        default=None, max_digits=16, decimal_places=4, allow_inf_nan=False
    )
    current_value: Decimal | None = Field(
        default=None, max_digits=16, decimal_places=4, allow_inf_nan=False
    )
    target_date: date | None = None

    @field_validator("target_value", mode="before")
    @classmethod
    def reject_null_target(cls, value: object) -> object:
        if value is None:
            raise ValueError("Target value cannot be null")
        return value


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal_id: UUID | None = None
    title: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=3000)
    due_date: date | None = None


class TaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: TaskStatus


class HabitCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal_id: UUID | None = None
    cue: str = Field(min_length=1, max_length=160)
    action: str = Field(min_length=1, max_length=240)
    frequency: Literal["daily", "weekly", "custom"]
    custom_schedule: str | None = Field(default=None, max_length=160)
    minimum_version: str = Field(min_length=1, max_length=240)
    recovery_action: str = Field(min_length=1, max_length=240)

    @model_validator(mode="after")
    def require_custom_schedule(self) -> HabitCreate:
        if self.frequency == "custom" and not self.custom_schedule:
            raise ValueError("custom_schedule is required for custom frequency")
        return self


class EvidenceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal_id: UUID | None = None
    task_id: UUID | None = None
    summary: str = Field(min_length=1, max_length=500)
    artifact_ref: str | None = Field(default=None, max_length=500)


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "code": "resource_not_found",
            "message": "The requested resource was not found.",
        },
    )


def _audit(db: Session, user: User, action: str) -> None:
    db.add(AuditEvent(user_id=user.id, action=action))


def _metric_payload(metric: GoalMetric) -> dict[str, object]:
    return {
        "id": str(metric.id),
        "name": metric.name,
        "unit": metric.unit,
        "baseline_value": str(metric.baseline_value)
        if metric.baseline_value is not None
        else None,
        "target_value": str(metric.target_value),
        "current_value": str(metric.current_value)
        if metric.current_value is not None
        else None,
        "source": metric.source,
        "target_date": metric.target_date.isoformat() if metric.target_date else None,
    }


def _goal_payload(goal: Goal) -> dict[str, object]:
    return {
        "id": str(goal.id),
        "domain": goal.domain,
        "title": goal.title,
        "description": goal.description,
        "priority": goal.priority,
        "status": goal.status,
        "target_date": goal.target_date.isoformat() if goal.target_date else None,
        "metrics": [_metric_payload(metric) for metric in goal.metrics],
    }


def _task_payload(task: Task) -> dict[str, object]:
    return {
        "id": str(task.id),
        "goal_id": str(task.goal_id) if task.goal_id else None,
        "title": task.title,
        "description": task.description,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "status": task.status,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }


def _habit_payload(habit: Habit) -> dict[str, object]:
    return {
        "id": str(habit.id),
        "goal_id": str(habit.goal_id) if habit.goal_id else None,
        "cue": habit.cue,
        "action": habit.action,
        "frequency": habit.frequency,
        "custom_schedule": habit.custom_schedule,
        "minimum_version": habit.minimum_version,
        "recovery_action": habit.recovery_action,
        "is_active": habit.is_active,
    }


def _evidence_payload(evidence: Evidence) -> dict[str, object]:
    captured_at = evidence.captured_at
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=UTC)
    return {
        "id": str(evidence.id),
        "goal_id": str(evidence.goal_id) if evidence.goal_id else None,
        "task_id": str(evidence.task_id) if evidence.task_id else None,
        "source": evidence.source,
        "is_verified": evidence.is_verified,
        "summary": evidence.summary,
        "artifact_ref": evidence.artifact_ref,
        "captured_at": captured_at.isoformat(),
    }


def export_domain_data(
    db: Session, user_id: UUID
) -> dict[str, list[dict[str, object]]]:
    """Return all account-owned domain data in a portable JSON shape."""
    goals = db.scalars(
        select(Goal)
        .where(Goal.user_id == user_id)
        .options(selectinload(Goal.metrics))
        .order_by(Goal.created_at, Goal.id)
    ).all()
    tasks = db.scalars(
        select(Task).where(Task.user_id == user_id).order_by(Task.created_at, Task.id)
    ).all()
    habits = db.scalars(
        select(Habit)
        .where(Habit.user_id == user_id)
        .order_by(Habit.created_at, Habit.id)
    ).all()
    evidence = db.scalars(
        select(Evidence)
        .where(Evidence.user_id == user_id)
        .order_by(Evidence.captured_at, Evidence.id)
    ).all()
    return {
        "goals": [_goal_payload(goal) for goal in goals],
        "tasks": [_task_payload(task) for task in tasks],
        "habits": [_habit_payload(habit) for habit in habits],
        "evidence": [_evidence_payload(record) for record in evidence],
    }


@router.get("/domains")
def list_domains(_auth: Authenticated) -> list[dict[str, str]]:
    """Return the fixed product domains; Empire is an initiative layer, not a domain."""
    return [dict(domain) for domain in DOMAINS]


@router.get("/goals")
def list_goals(
    auth: Authenticated, db: Session = Depends(get_db)
) -> list[dict[str, object]]:
    """List goals owned by the signed-in account."""
    goals = db.scalars(
        select(Goal)
        .where(Goal.user_id == auth.user.id)
        .options(selectinload(Goal.metrics))
        .order_by(Goal.created_at, Goal.id)
    ).all()
    return [_goal_payload(goal) for goal in goals]


@router.post("/goals", status_code=201)
def create_goal(
    request: GoalCreate,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Create an account-owned goal with explicit metric units and baselines."""
    goal = Goal(
        user_id=auth.user.id,
        domain=request.domain,
        title=request.title,
        description=request.description,
        priority=request.priority,
        target_date=request.target_date,
        metrics=[
            GoalMetric(
                name=metric.name,
                unit=metric.unit,
                baseline_value=metric.baseline_value,
                target_value=metric.target_value,
                current_value=metric.current_value,
                target_date=metric.target_date or request.target_date,
            )
            for metric in request.metrics
        ],
    )
    db.add(goal)
    _audit(db, auth.user, "goal.created")
    db.commit()
    db.refresh(goal)
    return _goal_payload(goal)


@router.get("/goals/{goal_id}")
def get_goal(
    goal_id: UUID,
    auth: Authenticated,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Read a goal only when it belongs to the signed-in account."""
    goal = db.scalar(
        select(Goal)
        .where(Goal.id == goal_id, Goal.user_id == auth.user.id)
        .options(selectinload(Goal.metrics))
    )
    if goal is None:
        raise _not_found()
    return _goal_payload(goal)


@router.patch("/goals/{goal_id}")
def update_goal(
    goal_id: UUID,
    changes: GoalUpdate,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Update an owned goal without accepting a client-supplied owner ID."""
    goal = db.scalar(
        select(Goal)
        .where(Goal.id == goal_id, Goal.user_id == auth.user.id)
        .options(selectinload(Goal.metrics))
    )
    if goal is None:
        raise _not_found()
    for field, value in changes.model_dump(exclude_unset=True).items():
        setattr(goal, field, value)
    _audit(db, auth.user, "goal.updated")
    db.commit()
    return _goal_payload(goal)


@router.post("/goals/{goal_id}/metrics", status_code=201)
def add_goal_metric(
    goal_id: UUID,
    metric: MetricInput,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Add a unit-labelled metric to an owned goal."""
    goal = db.scalar(
        select(Goal).where(Goal.id == goal_id, Goal.user_id == auth.user.id)
    )
    if goal is None:
        raise _not_found()
    record = GoalMetric(
        goal_id=goal.id,
        name=metric.name,
        unit=metric.unit,
        baseline_value=metric.baseline_value,
        target_value=metric.target_value,
        current_value=metric.current_value,
        target_date=metric.target_date or goal.target_date,
    )
    db.add(record)
    _audit(db, auth.user, "goal.metric_added")
    db.commit()
    return _metric_payload(record)


@router.patch("/metrics/{metric_id}")
def update_goal_metric(
    metric_id: UUID,
    changes: MetricUpdate,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Update metric values only through their owning goal."""
    metric = db.scalar(
        select(GoalMetric)
        .join(Goal, Goal.id == GoalMetric.goal_id)
        .where(GoalMetric.id == metric_id, Goal.user_id == auth.user.id)
    )
    if metric is None:
        raise _not_found()
    for field, value in changes.model_dump(exclude_unset=True).items():
        setattr(metric, field, value)
    _audit(db, auth.user, "goal.metric_updated")
    db.commit()
    return _metric_payload(metric)


@router.get("/tasks")
def list_tasks(
    auth: Authenticated, db: Session = Depends(get_db)
) -> list[dict[str, object]]:
    """List tasks owned by the signed-in account."""
    tasks = db.scalars(
        select(Task)
        .where(Task.user_id == auth.user.id)
        .order_by(Task.created_at, Task.id)
    ).all()
    return [_task_payload(task) for task in tasks]


@router.post("/tasks", status_code=201)
def create_task(
    request: TaskCreate,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Create an owned task, optionally attached to an owned goal."""
    if (
        request.goal_id is not None
        and db.scalar(
            select(Goal.id).where(
                Goal.id == request.goal_id, Goal.user_id == auth.user.id
            )
        )
        is None
    ):
        raise _not_found()
    task = Task(
        user_id=auth.user.id,
        goal_id=request.goal_id,
        title=request.title,
        description=request.description,
        due_date=request.due_date,
    )
    db.add(task)
    _audit(db, auth.user, "task.created")
    db.commit()
    return _task_payload(task)


@router.patch("/tasks/{task_id}")
def update_task(
    task_id: UUID,
    changes: TaskUpdate,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Update completion state for an owned task."""
    task = db.scalar(
        select(Task).where(Task.id == task_id, Task.user_id == auth.user.id)
    )
    if task is None:
        raise _not_found()
    old_status = task.status
    if old_status == changes.status:
        return _task_payload(task)
    record_task_transition(db, task, old_status, changes.status)
    task.status = changes.status
    task.completed_at = datetime.now(UTC) if changes.status == "completed" else None
    _audit(db, auth.user, "task.updated")
    db.commit()
    return _task_payload(task)


@router.get("/habits")
def list_habits(
    auth: Authenticated, db: Session = Depends(get_db)
) -> list[dict[str, object]]:
    """List habits owned by the signed-in account."""
    habits = db.scalars(
        select(Habit)
        .where(Habit.user_id == auth.user.id)
        .order_by(Habit.created_at, Habit.id)
    ).all()
    return [_habit_payload(habit) for habit in habits]


@router.post("/habits", status_code=201)
def create_habit(
    request: HabitCreate,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Create a repeatable habit with a minimum version and recovery action."""
    if (
        request.goal_id is not None
        and db.scalar(
            select(Goal.id).where(
                Goal.id == request.goal_id, Goal.user_id == auth.user.id
            )
        )
        is None
    ):
        raise _not_found()
    habit = Habit(
        user_id=auth.user.id,
        goal_id=request.goal_id,
        cue=request.cue,
        action=request.action,
        frequency=request.frequency,
        custom_schedule=request.custom_schedule,
        minimum_version=request.minimum_version,
        recovery_action=request.recovery_action,
    )
    db.add(habit)
    _audit(db, auth.user, "habit.created")
    db.commit()
    return _habit_payload(habit)


@router.get("/evidence")
def list_evidence(
    auth: Authenticated, db: Session = Depends(get_db)
) -> list[dict[str, object]]:
    """List evidence owned by the signed-in account."""
    records = db.scalars(
        select(Evidence)
        .where(Evidence.user_id == auth.user.id)
        .order_by(Evidence.captured_at, Evidence.id)
    ).all()
    return [_evidence_payload(record) for record in records]


@router.post("/evidence", status_code=201)
def create_evidence(
    request: EvidenceCreate,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Add self-reported evidence after checking all related record ownership."""
    goal = None
    task = None
    if request.goal_id is not None:
        goal = db.scalar(
            select(Goal).where(Goal.id == request.goal_id, Goal.user_id == auth.user.id)
        )
        if goal is None:
            raise _not_found()
    if request.task_id is not None:
        task = db.scalar(
            select(Task).where(Task.id == request.task_id, Task.user_id == auth.user.id)
        )
        if task is None:
            raise _not_found()
        if goal is not None and task.goal_id != goal.id:
            raise _not_found()
        if goal is None and task.goal_id is not None:
            goal = db.scalar(
                select(Goal).where(
                    Goal.id == task.goal_id,
                    Goal.user_id == auth.user.id,
                )
            )
            if goal is None:
                raise _not_found()

    record = Evidence(
        user_id=auth.user.id,
        goal_id=goal.id if goal else None,
        task_id=task.id if task else None,
        source="self_report",
        summary=request.summary,
        artifact_ref=request.artifact_ref,
        is_verified=False,
    )
    db.add(record)
    _audit(db, auth.user, "evidence.recorded")
    db.commit()
    return _evidence_payload(record)
