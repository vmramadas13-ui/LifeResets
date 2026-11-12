"""Account-scoped goal, task, habit, and evidence endpoints."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from liferesets.database import get_db
from liferesets.models import (
    AuditEvent,
    AwakeningBaselineGoalLink,
    DomainSubarea,
    Evidence,
    Goal,
    GoalMetric,
    Habit,
    HabitCheckIn,
    MetricMeasurement,
    Profile,
    Task,
    User,
)
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
DOMAIN_SETTINGS_KEY = "life_domains"

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
    confidence: int = Field(default=50, ge=0, le=100)
    measured_on: date | None = None
    target_date: date | None = None


class DomainPreferenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: DomainCode
    name: str = Field(min_length=1, max_length=80)
    sort_order: int = Field(ge=0, le=7)
    enabled: bool

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Domain name cannot be blank")
        return value


class DomainSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domains: list[DomainPreferenceInput] = Field(min_length=8, max_length=8)

    @model_validator(mode="after")
    def valid_domain_layout(self) -> DomainSettingsUpdate:
        codes = [item.code for item in self.domains]
        orders = [item.sort_order for item in self.domains]
        names = [item.name.casefold() for item in self.domains]
        if len(set(codes)) != len(DOMAINS):
            raise ValueError("Each built-in life area must appear exactly once")
        if set(codes) != {item["code"] for item in DOMAINS}:
            raise ValueError("All built-in life areas must be included")
        if set(orders) != set(range(len(DOMAINS))):
            raise ValueError("Display order must contain each position from 0 to 7")
        if len(set(names)) != len(names):
            raise ValueError("Life area names must be unique")
        if not any(item.enabled for item in self.domains):
            raise ValueError("At least one life area must stay available")
        return self


class DomainSubareaInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def trim_subarea_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Subarea name cannot be blank")
        return value


class GoalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: DomainCode
    subarea_id: UUID | None = None
    title: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=5000)
    priority: int = Field(default=3, ge=1, le=5)
    target_date: date | None = None
    metrics: list[MetricInput] = Field(default_factory=list, max_length=12)


class GoalUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=160)
    subarea_id: UUID | None = None
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

    @field_validator("title")
    @classmethod
    def trim_title(cls, value: str | None) -> str | None:
        value = value.strip() if value is not None else value
        if value == "":
            raise ValueError("Goal title cannot be blank")
        return value

    @field_validator("description")
    @classmethod
    def trim_description(cls, value: str | None) -> str | None:
        value = value.strip() if value is not None else value
        return value or None


class MetricUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    unit: str | None = Field(default=None, min_length=1, max_length=40)
    baseline_value: Decimal | None = Field(
        default=None, max_digits=16, decimal_places=4, allow_inf_nan=False
    )
    target_value: Decimal | None = Field(
        default=None, max_digits=16, decimal_places=4, allow_inf_nan=False
    )
    current_value: Decimal | None = Field(
        default=None, max_digits=16, decimal_places=4, allow_inf_nan=False
    )
    confidence: int | None = Field(default=None, ge=0, le=100)
    measured_on: date | None = None
    target_date: date | None = None

    @field_validator("name", "unit", "target_value", mode="before")
    @classmethod
    def reject_null_required_fields(cls, value: object) -> object:
        if value is None:
            raise ValueError("This field cannot be null")
        return value

    @field_validator("name", "unit")
    @classmethod
    def trim_labels(cls, value: str | None) -> str | None:
        value = value.strip() if value is not None else value
        if value == "":
            raise ValueError("This field cannot be blank")
        return value


class MetricMeasurementInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Decimal = Field(max_digits=16, decimal_places=4, allow_inf_nan=False)
    measured_on: date = Field(default_factory=date.today)
    confidence: int = Field(default=50, ge=0, le=100)


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
    weekdays: list[int] = Field(default_factory=list, max_length=7)
    interval_days: int | None = Field(default=None, ge=1, le=365)
    start_date: date = Field(default_factory=date.today)
    end_date: date | None = None
    reminder_preference: Literal["none", "in_app"] = "none"
    minimum_version: str = Field(min_length=1, max_length=240)
    recovery_action: str = Field(min_length=1, max_length=240)

    @field_validator("weekdays")
    @classmethod
    def valid_weekdays(cls, values: list[int]) -> list[int]:
        if len(set(values)) != len(values) or any(
            weekday < 1 or weekday > 7 for weekday in values
        ):
            raise ValueError("weekdays must contain unique ISO day numbers from 1 to 7")
        return sorted(values)

    @model_validator(mode="after")
    def valid_recurrence(self) -> HabitCreate:
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if self.frequency == "daily" and (self.weekdays or self.interval_days):
            raise ValueError("daily frequency cannot include weekdays or an interval")
        if self.frequency == "weekly" and self.interval_days is not None:
            raise ValueError("weekly frequency cannot include an interval")
        if self.frequency == "custom" and self.weekdays:
            raise ValueError("custom interval frequency cannot include weekdays")
        if (
            self.frequency == "custom"
            and self.interval_days is None
            and not self.custom_schedule
        ):
            raise ValueError("interval_days is required for a custom frequency")
        return self


class HabitUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_active: bool


class HabitCheckInInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["completed", "skipped"]
    recorded_on: date = Field(default_factory=date.today)
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("reason")
    @classmethod
    def blank_reason_is_empty(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


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


def _domain_payloads(db: Session, user_id: UUID) -> list[dict[str, object]]:
    profile = db.get(Profile, user_id)
    preferences = profile.preferences if profile and profile.preferences else {}
    saved = preferences.get(DOMAIN_SETTINGS_KEY, {})
    if not isinstance(saved, dict):
        saved = {}
    subareas_by_domain: dict[str, list[dict[str, str]]] = {}
    subareas = db.scalars(
        select(DomainSubarea)
        .where(DomainSubarea.user_id == user_id)
        .order_by(DomainSubarea.domain, DomainSubarea.name, DomainSubarea.id)
    ).all()
    for subarea in subareas:
        subareas_by_domain.setdefault(subarea.domain, []).append(
            {"id": str(subarea.id), "name": subarea.name}
        )
    entries = []
    for index, domain in enumerate(DOMAINS):
        override = saved.get(domain["code"], {})
        if not isinstance(override, dict):
            override = {}
        name = override.get("name")
        sort_order = override.get("sort_order", index)
        enabled = override.get("enabled", True)
        if not isinstance(name, str) or not name.strip():
            name = domain["name"]
        if not isinstance(sort_order, int) or not 0 <= sort_order < len(DOMAINS):
            sort_order = index
        if not isinstance(enabled, bool):
            enabled = True
        entries.append(
            {
                **domain,
                "name": name,
                "sort_order": sort_order,
                "enabled": enabled,
                "subareas": subareas_by_domain.get(domain["code"], []),
            }
        )
    return sorted(entries, key=lambda item: (item["sort_order"], item["code"]))


def _metric_measurement_payload(
    measurement: MetricMeasurement,
) -> dict[str, object]:
    return {
        "id": str(measurement.id),
        "value": str(measurement.value),
        "measured_on": measurement.recorded_on.isoformat(),
        "confidence": measurement.confidence,
        "source": measurement.source,
    }


def _measurement_sort_key(
    measurement: MetricMeasurement,
) -> tuple[date, datetime, str]:
    created_at = measurement.created_at
    if created_at.tzinfo is not None:
        created_at = created_at.astimezone(UTC).replace(tzinfo=None)
    return measurement.recorded_on, created_at, str(measurement.id)


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
        "confidence": metric.confidence,
        "source": metric.source,
        "target_date": metric.target_date.isoformat() if metric.target_date else None,
        "history": [
            _metric_measurement_payload(item)
            for item in sorted(
                metric.measurements,
                key=_measurement_sort_key,
                reverse=True,
            )
        ],
    }


def _metric_from_input(metric: MetricInput, target_date: date | None) -> GoalMetric:
    record = GoalMetric(
        name=metric.name,
        unit=metric.unit,
        baseline_value=metric.baseline_value,
        target_value=metric.target_value,
        current_value=metric.current_value,
        confidence=metric.confidence,
        target_date=metric.target_date or target_date,
    )
    if metric.current_value is not None:
        record.measurements.append(
            MetricMeasurement(
                value=metric.current_value,
                recorded_on=metric.measured_on or date.today(),
                confidence=metric.confidence,
            )
        )
    return record


def _goal_payload(goal: Goal) -> dict[str, object]:
    return {
        "id": str(goal.id),
        "domain": goal.domain,
        "subarea_id": str(goal.subarea_id) if goal.subarea_id else None,
        "subarea_name": goal.subarea.name if goal.subarea is not None else None,
        "title": goal.title,
        "description": goal.description,
        "priority": goal.priority,
        "status": goal.status,
        "target_date": goal.target_date.isoformat() if goal.target_date else None,
        "metrics": [_metric_payload(metric) for metric in goal.metrics],
        "starting_points": [
            {
                "id": str(link.baseline.id),
                "domain": link.baseline.domain,
                "metric_name": link.baseline.metric_name,
                "status": link.baseline.status,
                "value": (
                    str(link.baseline.value)
                    if link.baseline.value is not None
                    else None
                ),
                "unit": link.baseline.unit,
                "measured_on": (
                    link.baseline.measured_on.isoformat()
                    if link.baseline.measured_on
                    else None
                ),
            }
            for link in sorted(
                goal.baseline_links, key=lambda item: (item.linked_at, item.baseline_id)
            )
        ],
    }


def _habit_date_in_range(habit: Habit, on_date: date) -> bool:
    return not (
        (habit.start_date is not None and on_date < habit.start_date)
        or (habit.end_date is not None and on_date > habit.end_date)
    )


def _habit_occurs_on(habit: Habit, on_date: date) -> bool:
    if habit.frequency == "daily":
        return True
    if habit.frequency == "weekly":
        return not habit.weekdays or on_date.isoweekday() in habit.weekdays
    if habit.interval_days is None:
        # Older custom routines used a free-text schedule that cannot be
        # interpreted safely, so keep them manually loggable.
        return True
    anchor = habit.start_date or habit.created_at.date()
    return (on_date - anchor).days >= 0 and (
        on_date - anchor
    ).days % habit.interval_days == 0


def _habit_due_on(habit: Habit, on_date: date) -> bool:
    if not habit.is_active or not _habit_date_in_range(habit, on_date):
        return False
    if not _habit_occurs_on(habit, on_date):
        return False
    if habit.frequency == "weekly" and not habit.weekdays:
        week_start = on_date - timedelta(days=on_date.isoweekday() - 1)
        has_earlier_check_in = any(
            week_start <= item.recorded_on < on_date for item in habit.check_ins
        )
        return not has_earlier_check_in
    return True


def _next_habit_due_on(habit: Habit, from_date: date) -> date | None:
    if not habit.is_active:
        return None
    for offset in range(367):
        candidate = from_date + timedelta(days=offset)
        if habit.end_date is not None and candidate > habit.end_date:
            return None
        if _habit_due_on(habit, candidate):
            return candidate
    return None


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
    today = date.today()
    next_due_on = _next_habit_due_on(habit, today)
    return {
        "id": str(habit.id),
        "goal_id": str(habit.goal_id) if habit.goal_id else None,
        "cue": habit.cue,
        "action": habit.action,
        "frequency": habit.frequency,
        "custom_schedule": habit.custom_schedule,
        "weekdays": list(habit.weekdays or []),
        "interval_days": habit.interval_days,
        "start_date": habit.start_date.isoformat() if habit.start_date else None,
        "end_date": habit.end_date.isoformat() if habit.end_date else None,
        "reminder_preference": habit.reminder_preference,
        "schedule_configured": habit.frequency != "custom"
        or habit.interval_days is not None,
        "due_today": _habit_due_on(habit, today),
        "next_due_on": next_due_on.isoformat() if next_due_on else None,
        "minimum_version": habit.minimum_version,
        "recovery_action": habit.recovery_action,
        "is_active": habit.is_active,
        "check_ins": [
            _habit_checkin_payload(item)
            for item in sorted(
                habit.check_ins,
                key=_habit_checkin_sort_key,
                reverse=True,
            )
        ],
    }


def _habit_checkin_payload(check_in: HabitCheckIn) -> dict[str, object]:
    return {
        "id": str(check_in.id),
        "recorded_on": check_in.recorded_on.isoformat(),
        "status": check_in.status,
        "reason": check_in.reason,
        "created_at": check_in.created_at.isoformat(),
    }


def _habit_checkin_sort_key(
    check_in: HabitCheckIn,
) -> tuple[date, datetime, str]:
    created_at = check_in.created_at
    if created_at.tzinfo is not None:
        created_at = created_at.astimezone(UTC).replace(tzinfo=None)
    return check_in.recorded_on, created_at, str(check_in.id)


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
    subareas = db.scalars(
        select(DomainSubarea)
        .where(DomainSubarea.user_id == user_id)
        .order_by(DomainSubarea.domain, DomainSubarea.name, DomainSubarea.id)
    ).all()
    goals = db.scalars(
        select(Goal)
        .where(Goal.user_id == user_id)
        .options(
            selectinload(Goal.subarea),
            selectinload(Goal.metrics).selectinload(GoalMetric.measurements),
            selectinload(Goal.baseline_links).selectinload(
                AwakeningBaselineGoalLink.baseline
            ),
        )
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
        "subareas": [
            {
                "id": str(item.id),
                "domain": item.domain,
                "name": item.name,
            }
            for item in subareas
        ],
        "goals": [_goal_payload(goal) for goal in goals],
        "tasks": [_task_payload(task) for task in tasks],
        "habits": [_habit_payload(habit) for habit in habits],
        "evidence": [_evidence_payload(record) for record in evidence],
    }


@router.get("/domains")
def list_domains(
    auth: Authenticated, db: Session = Depends(get_db)
) -> list[dict[str, object]]:
    """Return the signed-in user's names, order, and visibility for life areas."""
    return _domain_payloads(db, auth.user.id)


@router.post("/domains/{domain}/subareas", status_code=201)
def create_domain_subarea(
    domain: DomainCode,
    request: DomainSubareaInput,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Create one named subarea under an account-owned built-in life area."""
    duplicate = db.scalar(
        select(DomainSubarea.id).where(
            DomainSubarea.user_id == auth.user.id,
            DomainSubarea.domain == domain,
            func.lower(DomainSubarea.name) == request.name.casefold(),
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=409, detail="A subarea with that name already exists"
        )
    subarea = DomainSubarea(user_id=auth.user.id, domain=domain, name=request.name)
    db.add(subarea)
    _audit(db, auth.user, "domain.subarea_created")
    db.commit()
    db.refresh(subarea)
    return {"id": str(subarea.id), "domain": subarea.domain, "name": subarea.name}


@router.patch("/domains/subareas/{subarea_id}")
def update_domain_subarea(
    subarea_id: UUID,
    changes: DomainSubareaInput,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Rename a subarea only when it belongs to the signed-in account."""
    subarea = db.scalar(
        select(DomainSubarea).where(
            DomainSubarea.id == subarea_id,
            DomainSubarea.user_id == auth.user.id,
        )
    )
    if subarea is None:
        raise _not_found()
    duplicate = db.scalar(
        select(DomainSubarea.id).where(
            DomainSubarea.user_id == auth.user.id,
            DomainSubarea.domain == subarea.domain,
            DomainSubarea.id != subarea_id,
            func.lower(DomainSubarea.name) == changes.name.casefold(),
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=409, detail="A subarea with that name already exists"
        )
    subarea.name = changes.name
    _audit(db, auth.user, "domain.subarea_renamed")
    db.commit()
    return {"id": str(subarea.id), "domain": subarea.domain, "name": subarea.name}


@router.delete("/domains/subareas/{subarea_id}")
def delete_domain_subarea(
    subarea_id: UUID,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, int | bool]:
    """Delete an owned subarea while preserving its goals without a subarea."""
    subarea = db.scalar(
        select(DomainSubarea).where(
            DomainSubarea.id == subarea_id,
            DomainSubarea.user_id == auth.user.id,
        )
    )
    if subarea is None:
        raise _not_found()
    goals = db.scalars(
        select(Goal).where(
            Goal.user_id == auth.user.id,
            Goal.subarea_id == subarea_id,
        )
    ).all()
    for goal in goals:
        goal.subarea_id = None
    db.delete(subarea)
    _audit(db, auth.user, "domain.subarea_deleted")
    db.commit()
    return {"deleted": True, "unassigned_goals": len(goals)}


@router.put("/domains/settings")
def update_domain_settings(
    changes: DomainSettingsUpdate,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    """Save a complete, account-owned layout for the eight built-in life areas."""
    profile = db.get(Profile, auth.user.id)
    if profile is None:
        profile = Profile(user_id=auth.user.id)
        db.add(profile)
    preferences = dict(profile.preferences or {})
    preferences[DOMAIN_SETTINGS_KEY] = {
        item.code: {
            "name": item.name,
            "sort_order": item.sort_order,
            "enabled": item.enabled,
        }
        for item in changes.domains
    }
    profile.preferences = preferences
    profile.updated_at = datetime.now(UTC)
    _audit(db, auth.user, "domain.settings_updated")
    db.commit()
    return _domain_payloads(db, auth.user.id)


@router.get("/goals")
def list_goals(
    auth: Authenticated, db: Session = Depends(get_db)
) -> list[dict[str, object]]:
    """List goals owned by the signed-in account."""
    goals = db.scalars(
        select(Goal)
        .where(Goal.user_id == auth.user.id)
        .options(
            selectinload(Goal.subarea),
            selectinload(Goal.metrics).selectinload(GoalMetric.measurements),
            selectinload(Goal.baseline_links).selectinload(
                AwakeningBaselineGoalLink.baseline
            ),
        )
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
    if request.domain not in {
        item["code"] for item in _domain_payloads(db, auth.user.id) if item["enabled"]
    }:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "domain_disabled",
                "message": "Choose an enabled life area for a new goal.",
            },
        )
    subarea = None
    if request.subarea_id is not None:
        subarea = db.scalar(
            select(DomainSubarea).where(
                DomainSubarea.id == request.subarea_id,
                DomainSubarea.user_id == auth.user.id,
            )
        )
        if subarea is None:
            raise _not_found()
        if subarea.domain != request.domain:
            raise HTTPException(
                status_code=422,
                detail="Choose a subarea within the selected life area.",
            )
    goal = Goal(
        user_id=auth.user.id,
        domain=request.domain,
        subarea_id=subarea.id if subarea is not None else None,
        title=request.title,
        description=request.description,
        priority=request.priority,
        target_date=request.target_date,
        metrics=[
            _metric_from_input(metric, request.target_date)
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
        .options(
            selectinload(Goal.subarea),
            selectinload(Goal.metrics).selectinload(GoalMetric.measurements),
            selectinload(Goal.baseline_links).selectinload(
                AwakeningBaselineGoalLink.baseline
            ),
        )
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
        .options(
            selectinload(Goal.subarea),
            selectinload(Goal.metrics).selectinload(GoalMetric.measurements),
        )
    )
    if goal is None:
        raise _not_found()
    updates = changes.model_dump(exclude_unset=True)
    if "subarea_id" in updates and updates["subarea_id"] is not None:
        subarea = db.scalar(
            select(DomainSubarea).where(
                DomainSubarea.id == updates["subarea_id"],
                DomainSubarea.user_id == auth.user.id,
            )
        )
        if subarea is None:
            raise _not_found()
        if subarea.domain != goal.domain:
            raise HTTPException(
                status_code=422,
                detail="Choose a subarea within the goal's life area.",
            )
    for field, value in updates.items():
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
    record = _metric_from_input(metric, goal.target_date)
    record.goal_id = goal.id
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
        .options(selectinload(GoalMetric.measurements))
    )
    if metric is None:
        raise _not_found()
    updates = changes.model_dump(exclude_unset=True)
    if "unit" in updates and updates["unit"] != metric.unit and metric.measurements:
        raise HTTPException(
            status_code=409,
            detail=(
                "A measure's unit cannot change after dated values exist. "
                "Add a separate measure to preserve the history."
            ),
        )
    measured_on = updates.pop("measured_on", None)
    confidence = updates.pop("confidence", None)
    current_value_sent = "current_value" in changes.model_fields_set
    current_value = updates.pop("current_value", None)
    measurement_record: MetricMeasurement | None = None
    for field, value in updates.items():
        setattr(metric, field, value)
    if current_value_sent and changes.current_value is not None:
        existing_latest = max(
            metric.measurements,
            key=_measurement_sort_key,
            default=None,
        )
        measurement_date = measured_on or date.today()
        measurement_record = MetricMeasurement(
            value=current_value,
            recorded_on=measurement_date,
            confidence=confidence if confidence is not None else metric.confidence,
        )
        metric.measurements.append(measurement_record)
        if existing_latest is None or measurement_date >= existing_latest.recorded_on:
            metric.current_value = current_value
            if confidence is not None:
                metric.confidence = confidence
            metric.source = "self_report"
    elif current_value_sent:
        metric.current_value = None
    elif confidence is not None:
        metric.confidence = confidence
    _audit(db, auth.user, "goal.metric_updated")
    db.commit()
    if measurement_record is not None:
        db.refresh(measurement_record)
    db.refresh(metric)
    return _metric_payload(metric)


@router.get("/metrics/{metric_id}/history")
def list_metric_history(
    metric_id: UUID,
    auth: Authenticated,
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    """List dated values only when the metric belongs to the signed-in account."""
    metric = db.scalar(
        select(GoalMetric)
        .join(Goal, Goal.id == GoalMetric.goal_id)
        .where(GoalMetric.id == metric_id, Goal.user_id == auth.user.id)
    )
    if metric is None:
        raise _not_found()
    return [
        _metric_measurement_payload(item)
        for item in sorted(
            metric.measurements,
            key=_measurement_sort_key,
            reverse=True,
        )
    ]


@router.post("/metrics/{metric_id}/measurements", status_code=201)
def add_metric_measurement(
    metric_id: UUID,
    measurement: MetricMeasurementInput,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Append a self-reported measurement and update its current-value summary."""
    metric = db.scalar(
        select(GoalMetric)
        .join(Goal, Goal.id == GoalMetric.goal_id)
        .where(GoalMetric.id == metric_id, Goal.user_id == auth.user.id)
    )
    if metric is None:
        raise _not_found()
    record = MetricMeasurement(
        value=measurement.value,
        recorded_on=measurement.measured_on,
        confidence=measurement.confidence,
    )
    latest_existing = max(
        metric.measurements,
        key=_measurement_sort_key,
        default=None,
    )
    if (
        latest_existing is None
        or measurement.measured_on >= latest_existing.recorded_on
    ):
        metric.current_value = measurement.value
        metric.confidence = measurement.confidence
        metric.source = "self_report"
    metric.measurements.append(record)
    _audit(db, auth.user, "goal.metric_measured")
    db.commit()
    db.refresh(record)
    return _metric_measurement_payload(record)


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
        .options(selectinload(Habit.check_ins))
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
        weekdays=request.weekdays,
        interval_days=request.interval_days,
        start_date=request.start_date,
        end_date=request.end_date,
        reminder_preference=request.reminder_preference,
        minimum_version=request.minimum_version,
        recovery_action=request.recovery_action,
    )
    db.add(habit)
    _audit(db, auth.user, "habit.created")
    db.commit()
    return _habit_payload(habit)


@router.patch("/habits/{habit_id}")
def update_habit(
    habit_id: UUID,
    changes: HabitUpdate,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Pause or resume an owned habit without removing its history."""
    habit = db.scalar(
        select(Habit)
        .where(Habit.id == habit_id, Habit.user_id == auth.user.id)
        .options(selectinload(Habit.check_ins))
    )
    if habit is None:
        raise _not_found()
    habit.is_active = changes.is_active
    _audit(db, auth.user, "habit.status_updated")
    db.commit()
    return _habit_payload(habit)


@router.get("/habits/{habit_id}/check-ins")
def list_habit_check_ins(
    habit_id: UUID,
    auth: Authenticated,
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    """Return the check-in history for one of the signed-in user's habits."""
    habit = db.scalar(
        select(Habit)
        .where(Habit.id == habit_id, Habit.user_id == auth.user.id)
        .options(selectinload(Habit.check_ins))
    )
    if habit is None:
        raise _not_found()
    return [
        _habit_checkin_payload(item)
        for item in sorted(habit.check_ins, key=_habit_checkin_sort_key, reverse=True)
    ]


@router.post("/habits/{habit_id}/check-ins", status_code=201)
def record_habit_check_in(
    habit_id: UUID,
    check_in: HabitCheckInInput,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Append a completed or skipped habit entry with an optional note."""
    habit = db.scalar(
        select(Habit)
        .where(Habit.id == habit_id, Habit.user_id == auth.user.id)
        .options(selectinload(Habit.check_ins))
    )
    if habit is None:
        raise _not_found()
    if not _habit_due_on(habit, check_in.recorded_on):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "habit_not_due",
                "message": "This routine is not scheduled for that date.",
            },
        )
    record = HabitCheckIn(
        recorded_on=check_in.recorded_on,
        status=check_in.status,
        reason=check_in.reason,
    )
    habit.check_ins.append(record)
    _audit(db, auth.user, "habit.checked_in")
    db.commit()
    db.refresh(record)
    return _habit_checkin_payload(record)


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
