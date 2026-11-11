"""Character profile, transparent progression, skills, and Chronicle."""

from __future__ import annotations

from datetime import UTC
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from liferesets.database import get_db
from liferesets.models import (
    AuditEvent,
    ProgressionEvent,
    ProgressionSettings,
    Skill,
    SkillEvidence,
    Task,
    User,
)
from liferesets.progression import (
    RANK_THRESHOLDS,
    RULESET_VERSION,
    XP_PER_LEVEL,
    XP_PER_TASK,
)
from liferesets.security import Authenticated, AuthenticatedWithCsrf

router = APIRouter(prefix="/api/v1/rpg", tags=["character progression"])
Domain = Literal[
    "career",
    "fitness",
    "finance",
    "discipline",
    "learning",
    "mental_wellness",
    "relationships",
    "lifestyle",
]


class CharacterUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hunter_name: str | None = Field(default=None, min_length=1, max_length=80)
    callsign: str | None = Field(default=None, max_length=80)
    paused: bool | None = None

    @field_validator("hunter_name", "paused", mode="before")
    @classmethod
    def reject_null_required_fields(cls, value: object) -> object:
        if value is None:
            raise ValueError("This field cannot be null")
        return value


class SkillCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    domain: Domain | None = None
    name: str = Field(min_length=1, max_length=80)
    definition: str = Field(min_length=1, max_length=500)
    level: int = Field(default=1, ge=1, le=10)
    confidence: int = Field(default=0, ge=0, le=100)


class SkillUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    domain: Domain | None = None
    name: str | None = Field(default=None, min_length=1, max_length=80)
    definition: str | None = Field(default=None, min_length=1, max_length=500)
    level: int | None = Field(default=None, ge=1, le=10)
    confidence: int | None = Field(default=None, ge=0, le=100)

    @field_validator("name", "definition", "level", "confidence", mode="before")
    @classmethod
    def reject_null_required_fields(cls, value: object) -> object:
        if value is None:
            raise ValueError("This field cannot be null")
        return value


class SkillEvidenceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=1, max_length=500)
    artifact_ref: str | None = Field(default=None, max_length=500)
    confidence: int = Field(default=50, ge=0, le=100)


class ProgressionCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=5, max_length=240)


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "code": "resource_not_found",
            "message": "The requested record was not found.",
        },
    )


def _settings_payload(settings: ProgressionSettings | None) -> dict[str, object]:
    return {
        "hunter_name": settings.hunter_name if settings else "Hunter",
        "callsign": settings.callsign if settings else None,
        "paused": settings.paused if settings else False,
        "ruleset_version": settings.ruleset_version if settings else RULESET_VERSION,
    }


def _event_payload(event: ProgressionEvent) -> dict[str, object]:
    created_at = event.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return {
        "id": str(event.id),
        "task_id": str(event.task_id) if event.task_id else None,
        "correction_of_id": (
            str(event.correction_of_id) if event.correction_of_id else None
        ),
        "event_type": event.event_type,
        "xp_delta": event.xp_delta,
        "ruleset_version": event.ruleset_version,
        "reason": event.reason,
        "created_at": created_at.isoformat(),
    }


def _skill_payload(skill: Skill) -> dict[str, object]:
    return {
        "id": str(skill.id),
        "domain": skill.domain,
        "name": skill.name,
        "definition": skill.definition,
        "level": skill.level,
        "confidence": skill.confidence,
        "evidence": [
            {
                "id": str(item.id),
                "summary": item.summary,
                "artifact_ref": item.artifact_ref,
                "confidence": item.confidence,
                "source": "self_report",
                "verified": False,
                "captured_at": item.captured_at.isoformat(),
            }
            for item in sorted(skill.evidence, key=lambda item: item.captured_at)
        ],
    }


def _get_or_create_settings(db: Session, user: User) -> ProgressionSettings:
    settings = db.get(ProgressionSettings, user.id)
    if settings is None:
        settings = ProgressionSettings(user_id=user.id)
        db.add(settings)
        db.flush()
    return settings


@router.get("/status")
def rpg_status(auth: Authenticated, db: Session = Depends(get_db)) -> dict[str, object]:
    """Return the signed-in character's published, versioned progression state."""
    total_xp = int(
        db.scalar(
            select(func.coalesce(func.sum(ProgressionEvent.xp_delta), 0)).where(
                ProgressionEvent.user_id == auth.user.id
            )
        )
        or 0
    )
    total_xp = max(0, total_xp)
    completed = int(
        db.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.user_id == auth.user.id, Task.status == "completed")
        )
        or 0
    )
    settings = db.get(ProgressionSettings, auth.user.id)
    rank_index = max(
        index
        for index, (_, threshold) in enumerate(RANK_THRESHOLDS)
        if total_xp >= threshold
    )
    rank, rank_xp = RANK_THRESHOLDS[rank_index]
    if rank_index + 1 < len(RANK_THRESHOLDS):
        next_rank, next_xp = RANK_THRESHOLDS[rank_index + 1]
        rank_progress = round((total_xp - rank_xp) / (next_xp - rank_xp) * 100)
    else:
        next_rank, next_xp, rank_progress = None, None, 100

    achievements: list[str] = []
    if completed >= 1:
        achievements.append("first_completed_task")
    if completed >= 10:
        achievements.append("ten_completed_tasks")
    return {
        "character": _settings_payload(settings),
        "level": total_xp // XP_PER_LEVEL + 1,
        "rank": rank,
        "next_rank": next_rank,
        "rank_progress_percent": rank_progress,
        "total_xp": total_xp,
        "xp_in_level": total_xp % XP_PER_LEVEL,
        "xp_to_next_level": XP_PER_LEVEL - total_xp % XP_PER_LEVEL,
        "xp_per_level": XP_PER_LEVEL,
        "completed_tasks": completed,
        "achievements": achievements,
        "ruleset": {
            "version": settings.ruleset_version if settings else RULESET_VERSION,
            "xp_per_completed_task": XP_PER_TASK,
            "xp_per_level": XP_PER_LEVEL,
            "rank_thresholds": [
                {"rank": label, "minimum_xp": threshold}
                for label, threshold in RANK_THRESHOLDS
            ],
            "draft": True,
        },
        "meaning": "Activity progress only; this is not a score of personal worth.",
    }


@router.patch("/character")
def update_character(
    changes: CharacterUpdate,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Edit the player's Hunter identity and pause new XP awards."""
    settings = _get_or_create_settings(db, auth.user)
    before_paused = settings.paused
    for field, value in changes.model_dump(exclude_unset=True).items():
        setattr(settings, field, value)
    if before_paused != settings.paused:
        db.add(
            AuditEvent(
                user_id=auth.user.id,
                action="progression.paused"
                if settings.paused
                else "progression.resumed",
            )
        )
    db.commit()
    return _settings_payload(settings)


@router.get("/events")
def list_progression_events(
    auth: Authenticated,
    db: Session = Depends(get_db),
    limit: int = 50,
) -> list[dict[str, object]]:
    """List recent append-only XP awards and corrections for this account."""
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 100")
    events = db.scalars(
        select(ProgressionEvent)
        .where(ProgressionEvent.user_id == auth.user.id)
        .order_by(ProgressionEvent.created_at.desc(), ProgressionEvent.id.desc())
        .limit(limit)
    ).all()
    return [_event_payload(event) for event in events]


@router.post("/events/{event_id}/correct", status_code=201)
def correct_progression_event(
    event_id: UUID,
    request: ProgressionCorrection,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Append one equal-and-opposite entry; the original event remains visible."""
    original = db.scalar(
        select(ProgressionEvent).where(
            ProgressionEvent.id == event_id,
            ProgressionEvent.user_id == auth.user.id,
        )
    )
    if original is None:
        raise _not_found()
    if db.scalar(
        select(ProgressionEvent.id).where(
            ProgressionEvent.user_id == auth.user.id,
            ProgressionEvent.correction_of_id == original.id,
        )
    ):
        raise HTTPException(
            status_code=409, detail="This event already has a correction."
        )
    correction = ProgressionEvent(
        user_id=auth.user.id,
        task_id=original.task_id,
        correction_of_id=original.id,
        event_type="correction",
        xp_delta=-original.xp_delta,
        ruleset_version=original.ruleset_version,
        reason=request.reason,
    )
    db.add(correction)
    db.add(AuditEvent(user_id=auth.user.id, action="progression.corrected"))
    db.commit()
    db.refresh(correction)
    return _event_payload(correction)


@router.get("/skills")
def list_skills(
    auth: Authenticated, db: Session = Depends(get_db)
) -> list[dict[str, object]]:
    skills = db.scalars(
        select(Skill)
        .where(Skill.user_id == auth.user.id)
        .options(selectinload(Skill.evidence))
        .order_by(Skill.name, Skill.id)
    ).all()
    return [_skill_payload(skill) for skill in skills]


@router.post("/skills", status_code=201)
def create_skill(
    request: SkillCreate,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    duplicate = db.scalar(
        select(Skill.id).where(
            Skill.user_id == auth.user.id,
            func.lower(Skill.name) == request.name.strip().lower(),
        )
    )
    if duplicate:
        raise HTTPException(
            status_code=409, detail="A skill with this name already exists."
        )
    skill = Skill(
        user_id=auth.user.id,
        domain=request.domain,
        name=request.name.strip(),
        definition=request.definition.strip(),
        level=request.level,
        confidence=request.confidence,
    )
    db.add(skill)
    db.add(AuditEvent(user_id=auth.user.id, action="skill.created"))
    db.commit()
    db.refresh(skill)
    return _skill_payload(skill)


@router.patch("/skills/{skill_id}")
def update_skill(
    skill_id: UUID,
    changes: SkillUpdate,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    skill = db.scalar(
        select(Skill)
        .where(Skill.id == skill_id, Skill.user_id == auth.user.id)
        .options(selectinload(Skill.evidence))
    )
    if skill is None:
        raise _not_found()
    updates = changes.model_dump(exclude_unset=True)
    if "name" in updates:
        updates["name"] = updates["name"].strip()
    if "definition" in updates:
        updates["definition"] = updates["definition"].strip()
    for field, value in updates.items():
        setattr(skill, field, value)
    db.add(AuditEvent(user_id=auth.user.id, action="skill.updated"))
    db.commit()
    return _skill_payload(skill)


@router.post("/skills/{skill_id}/evidence", status_code=201)
def add_skill_evidence(
    skill_id: UUID,
    request: SkillEvidenceCreate,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    skill = db.scalar(
        select(Skill).where(Skill.id == skill_id, Skill.user_id == auth.user.id)
    )
    if skill is None:
        raise _not_found()
    evidence = SkillEvidence(
        user_id=auth.user.id,
        skill_id=skill.id,
        summary=request.summary.strip(),
        artifact_ref=request.artifact_ref,
        confidence=request.confidence,
    )
    db.add(evidence)
    db.add(AuditEvent(user_id=auth.user.id, action="skill.evidence_added"))
    db.commit()
    db.refresh(evidence)
    return {
        "id": str(evidence.id),
        "summary": evidence.summary,
        "artifact_ref": evidence.artifact_ref,
        "confidence": evidence.confidence,
        "source": "self_report",
        "verified": False,
        "captured_at": evidence.captured_at.isoformat(),
    }


@router.get("/chronicle")
def list_chronicle(
    auth: Authenticated, db: Session = Depends(get_db)
) -> list[dict[str, object]]:
    """Show a recent, account-scoped timeline without storing private request text."""
    action_titles = {
        "goal.created": "Goal added",
        "goal.updated": "Goal updated",
        "task.created": "Action added",
        "task.updated": "Action status changed",
        "daily_plan.item_updated": "Daily plan action updated",
        "campaign.created": "90-day focus started",
        "campaign.updated": "Campaign updated",
        "review.created": "Review started",
        "review.updated": "Review updated",
        "onboarding.step_updated": "Onboarding step updated",
        "skill.created": "Skill added",
        "skill.updated": "Skill updated",
        "skill.evidence_added": "Skill evidence added",
        "progression.corrected": "Progress record corrected",
        "progression.paused": "Game layer paused",
        "progression.resumed": "Game layer resumed",
    }
    audits = db.scalars(
        select(AuditEvent)
        .where(
            AuditEvent.user_id == auth.user.id,
            AuditEvent.action.in_(action_titles),
        )
        .order_by(AuditEvent.created_at.desc())
        .limit(100)
    ).all()
    events = db.scalars(
        select(ProgressionEvent)
        .where(ProgressionEvent.user_id == auth.user.id)
        .order_by(ProgressionEvent.created_at.desc())
        .limit(100)
    ).all()
    timeline = [
        {
            "id": str(event.id),
            "category": "progression",
            "title": event.reason,
            "detail": f"{event.xp_delta:+d} XP · {event.ruleset_version}",
            "created_at": event.created_at.isoformat(),
        }
        for event in events
    ] + [
        {
            "id": str(event.id),
            "category": "activity",
            "title": action_titles[event.action],
            "detail": None,
            "created_at": event.created_at.isoformat(),
        }
        for event in audits
    ]
    return sorted(timeline, key=lambda event: event["created_at"], reverse=True)[:100]


def export_character_data(db: Session, user_id: UUID) -> dict[str, object]:
    """Export character settings, the append-only progression ledger, and skills."""
    settings = db.get(ProgressionSettings, user_id)
    skills = db.scalars(
        select(Skill)
        .where(Skill.user_id == user_id)
        .options(selectinload(Skill.evidence))
        .order_by(Skill.name, Skill.id)
    ).all()
    events = db.scalars(
        select(ProgressionEvent)
        .where(ProgressionEvent.user_id == user_id)
        .order_by(ProgressionEvent.created_at, ProgressionEvent.id)
    ).all()
    return {
        "character": _settings_payload(settings),
        "progression_events": [_event_payload(event) for event in events],
        "skills": [_skill_payload(skill) for skill in skills],
    }
