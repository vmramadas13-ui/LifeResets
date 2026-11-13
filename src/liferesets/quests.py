"""Account-owned multi-step quests built from ordinary plannable tasks."""

from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from liferesets.database import get_db
from liferesets.models import AuditEvent, Goal, Quest, QuestStep, Task, User
from liferesets.security import Authenticated, AuthenticatedWithCsrf

router = APIRouter(prefix="/api/v1/quests", tags=["quests"])


class QuestStepInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=160)
    due_date: date | None = None

    @field_validator("title")
    @classmethod
    def trim_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Quest steps cannot be blank")
        return value


class QuestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=3000)
    goal_id: UUID | None = None
    steps: list[QuestStepInput] = Field(min_length=2, max_length=12)

    @field_validator("title")
    @classmethod
    def trim_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Quest title cannot be blank")
        return value

    @field_validator("description")
    @classmethod
    def trim_description(cls, value: str | None) -> str | None:
        value = value.strip() if value is not None else value
        return value or None


class QuestUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=3000)
    status: Literal["active", "archived"] | None = None

    @field_validator("title", "status", mode="before")
    @classmethod
    def reject_null_required_changes(cls, value: object) -> object:
        if value is None:
            raise ValueError("This field cannot be null")
        return value

    @field_validator("title")
    @classmethod
    def trim_title(cls, value: str | None) -> str | None:
        value = value.strip() if value is not None else value
        if value == "":
            raise ValueError("Quest title cannot be blank")
        return value

    @field_validator("description")
    @classmethod
    def trim_description(cls, value: str | None) -> str | None:
        value = value.strip() if value is not None else value
        return value or None

    @model_validator(mode="after")
    def require_a_change(self) -> QuestUpdate:
        if not self.model_fields_set:
            raise ValueError("Provide a quest field to update")
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


def _quest_payload(quest: Quest) -> dict[str, object]:
    steps = sorted(quest.steps, key=lambda item: item.position)
    completed = sum(step.task.status == "completed" for step in steps)
    status = (
        quest.status
        if quest.status == "archived"
        else "completed"
        if completed == len(steps)
        else "active"
    )
    return {
        "id": str(quest.id),
        "goal_id": str(quest.goal_id) if quest.goal_id else None,
        "title": quest.title,
        "description": quest.description,
        "status": status,
        "completed_steps": completed,
        "total_steps": len(steps),
        "progress_percent": round(completed * 100 / len(steps)) if steps else 0,
        "created_at": quest.created_at.isoformat(),
        "steps": [
            {
                "id": str(step.id),
                "task_id": str(step.task_id),
                "position": step.position,
                "title": step.task.title,
                "domain": step.task.domain,
                "status": step.task.status,
                "due_date": step.task.due_date.isoformat()
                if step.task.due_date
                else None,
            }
            for step in steps
        ],
    }


def _owned_quest(db: Session, user_id: UUID, quest_id: UUID) -> Quest | None:
    return db.scalar(
        select(Quest)
        .where(Quest.id == quest_id, Quest.user_id == user_id)
        .options(selectinload(Quest.steps).selectinload(QuestStep.task))
    )


@router.get("")
def list_quests(
    auth: Authenticated, db: Session = Depends(get_db)
) -> list[dict[str, object]]:
    quests = db.scalars(
        select(Quest)
        .where(Quest.user_id == auth.user.id)
        .options(selectinload(Quest.steps).selectinload(QuestStep.task))
        .order_by(Quest.created_at.desc(), Quest.id)
    ).all()
    return [_quest_payload(quest) for quest in quests]


@router.post("", status_code=201)
def create_quest(
    request: QuestCreate,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    goal = None
    if request.goal_id is not None:
        goal = db.scalar(
            select(Goal).where(Goal.id == request.goal_id, Goal.user_id == auth.user.id)
        )
        if goal is None:
            raise _not_found()
    task_domain = goal.domain if goal is not None else "discipline"

    quest = Quest(
        user_id=auth.user.id,
        goal_id=request.goal_id,
        title=request.title,
        description=request.description,
    )
    for position, step_input in enumerate(request.steps):
        task = Task(
            user_id=auth.user.id,
            goal_id=request.goal_id,
            domain=task_domain,
            title=step_input.title,
            due_date=step_input.due_date,
        )
        quest.steps.append(QuestStep(task=task, position=position))
    db.add(quest)
    _audit(db, auth.user, "quest.created")
    db.commit()
    quest = _owned_quest(db, auth.user.id, quest.id)
    assert quest is not None
    return _quest_payload(quest)


@router.get("/{quest_id}")
def get_quest(
    quest_id: UUID,
    auth: Authenticated,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    quest = _owned_quest(db, auth.user.id, quest_id)
    if quest is None:
        raise _not_found()
    return _quest_payload(quest)


@router.patch("/{quest_id}")
def update_quest(
    quest_id: UUID,
    changes: QuestUpdate,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    quest = _owned_quest(db, auth.user.id, quest_id)
    if quest is None:
        raise _not_found()
    for field, value in changes.model_dump(exclude_unset=True).items():
        setattr(quest, field, value)
    _audit(db, auth.user, "quest.updated")
    db.commit()
    return _quest_payload(quest)


def export_quests(db: Session, user_id: UUID) -> list[dict[str, object]]:
    quests = db.scalars(
        select(Quest)
        .where(Quest.user_id == user_id)
        .options(selectinload(Quest.steps).selectinload(QuestStep.task))
        .order_by(Quest.created_at, Quest.id)
    ).all()
    return [_quest_payload(quest) for quest in quests]
