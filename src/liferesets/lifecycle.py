"""Resumable onboarding, 90-day campaigns, and consent-aware reviews."""

from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from liferesets.database import get_db
from liferesets.models import (
    AuditEvent,
    Campaign,
    ConsentRecord,
    OnboardingStep,
    Review,
    User,
)
from liferesets.security import Authenticated, AuthenticatedWithCsrf

router = APIRouter(prefix="/api/v1", tags=["onboarding, campaigns, reviews"])
StepStatus = Literal["in_progress", "completed", "skipped"]
CampaignStatus = Literal["active", "paused", "completed", "archived"]
ReviewStatus = Literal["draft", "completed"]


class OnboardingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: StepStatus
    answer: str | None = Field(default=None, max_length=1200)


AWAKENING_PROMPTS = (
    {
        "title": "Choose your focus",
        "prompt": (
            "Which parts of life would you most like to give attention to right now?"
        ),
    },
    {
        "title": "Notice what is working",
        "prompt": "What is already helping you, and what would you like to keep?",
    },
    {
        "title": "Understand your capacity",
        "prompt": (
            "What amount of time and energy usually feels realistic for a small change?"
        ),
    },
    {
        "title": "Spot the friction",
        "prompt": "What tends to make it harder to follow through on plans?",
    },
    {
        "title": "Find useful support",
        "prompt": (
            "What tools, routines, or kinds of support make a fresh start easier?"
        ),
    },
    {
        "title": "Pick a first step",
        "prompt": "What is one small action that would feel manageable to try?",
    },
    {
        "title": "Choose how to review",
        "prompt": "How would you like to notice progress and adjust your plan?",
    },
)


class CampaignCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=160)
    objective: str = Field(min_length=1, max_length=2000)
    starts_on: date
    ends_on: date

    @model_validator(mode="after")
    def is_ninety_days(self) -> CampaignCreate:
        if (self.ends_on - self.starts_on).days != 89:
            raise ValueError(
                "A campaign must span 90 calendar days, including both dates"
            )
        return self


class CampaignUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: CampaignStatus


class ReviewResponses(BaseModel):
    model_config = ConfigDict(extra="forbid")
    wins: str | None = Field(default=None, max_length=1200)
    blockers: str | None = Field(default=None, max_length=1200)
    changes: str | None = Field(default=None, max_length=1200)
    next_step: str | None = Field(default=None, max_length=1200)


class ReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cadence: Literal["weekly", "monthly"]
    period_start: date
    period_end: date
    status: ReviewStatus = "draft"
    responses: ReviewResponses = Field(default_factory=ReviewResponses)

    @model_validator(mode="after")
    def valid_period(self) -> ReviewCreate:
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        return self


class ReviewUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: ReviewStatus | None = None
    responses: ReviewResponses | None = None


def _audit(db: Session, user: User, action: str) -> None:
    db.add(AuditEvent(user_id=user.id, action=action))


def _consent_active(db: Session, user_id: UUID, purpose: str) -> bool:
    latest = db.scalar(
        select(ConsentRecord)
        .where(ConsentRecord.user_id == user_id, ConsentRecord.purpose == purpose)
        .order_by(ConsentRecord.created_at.desc(), ConsentRecord.id.desc())
        .limit(1)
    )
    return bool(latest and latest.granted)


def _review_payload(review: Review) -> dict[str, object]:
    return {
        "id": str(review.id),
        "cadence": review.cadence,
        "period_start": review.period_start.isoformat(),
        "period_end": review.period_end.isoformat(),
        "status": review.status,
        "responses": review.responses,
    }


@router.get("/onboarding/awakening")
def get_awakening(
    auth: Authenticated, db: Session = Depends(get_db)
) -> dict[str, object]:
    """Read the resumable seven-prompt assessment and its consent state."""
    stored = {
        item.step_number: item
        for item in db.scalars(
            select(OnboardingStep).where(OnboardingStep.user_id == auth.user.id)
        ).all()
    }
    steps = [
        {
            "step": number,
            "day": number,
            "title": prompt["title"],
            "prompt": prompt["prompt"],
            "status": stored[number].status if number in stored else "not_started",
            "answer": stored[number].answer if number in stored else None,
        }
        for number, prompt in enumerate(AWAKENING_PROMPTS, start=1)
    ]
    return {
        "steps": steps,
        "completed": sum(item["status"] == "completed" for item in steps),
        "storage_consent": _consent_active(db, auth.user.id, "awakening_storage"),
    }


@router.patch("/onboarding/awakening/{step_number}")
def update_awakening_step(
    step_number: int,
    changes: OnboardingUpdate,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    if not 1 <= step_number <= 7:
        raise HTTPException(status_code=404, detail="Onboarding step not found")
    answer_was_sent = "answer" in changes.model_fields_set
    answer = changes.answer.strip() if changes.answer else ""
    if (
        answer_was_sent
        and answer
        and not _consent_active(db, auth.user.id, "awakening_storage")
    ):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "awakening_consent_required",
                "message": (
                    "Grant awakening_storage consent before saving Awakening answers."
                ),
            },
        )
    step = db.scalar(
        select(OnboardingStep).where(
            OnboardingStep.user_id == auth.user.id,
            OnboardingStep.step_number == step_number,
        )
    )
    if step is None:
        step = OnboardingStep(
            user_id=auth.user.id, step_number=step_number, status=changes.status
        )
        db.add(step)
    else:
        step.status = changes.status
    if answer_was_sent:
        step.answer = answer or None
    _audit(db, auth.user, "onboarding.step_updated")
    db.commit()
    return {"step": step_number, "status": step.status}


@router.delete("/onboarding/awakening/answers")
def delete_awakening_answers(
    auth: AuthenticatedWithCsrf, db: Session = Depends(get_db)
) -> dict[str, int]:
    """Remove all saved prompt answers while preserving progress markers."""
    steps = db.scalars(
        select(OnboardingStep).where(OnboardingStep.user_id == auth.user.id)
    ).all()
    deleted = 0
    for step in steps:
        if step.answer is not None:
            deleted += 1
            step.answer = None
    _audit(db, auth.user, "onboarding.answers_deleted")
    db.commit()
    return {"deleted_answers": deleted}


@router.get("/campaigns")
def list_campaigns(
    auth: Authenticated, db: Session = Depends(get_db)
) -> list[dict[str, object]]:
    campaigns = db.scalars(
        select(Campaign)
        .where(Campaign.user_id == auth.user.id)
        .order_by(Campaign.starts_on.desc())
    ).all()
    return [
        {
            "id": str(item.id),
            "title": item.title,
            "objective": item.objective,
            "starts_on": item.starts_on.isoformat(),
            "ends_on": item.ends_on.isoformat(),
            "status": item.status,
        }
        for item in campaigns
    ]


@router.post("/campaigns", status_code=201)
def create_campaign(
    request: CampaignCreate,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    campaign = Campaign(
        user_id=auth.user.id,
        title=request.title,
        objective=request.objective,
        starts_on=request.starts_on,
        ends_on=request.ends_on,
    )
    db.add(campaign)
    _audit(db, auth.user, "campaign.created")
    db.commit()
    db.refresh(campaign)
    return {
        "id": str(campaign.id),
        "title": campaign.title,
        "objective": campaign.objective,
        "starts_on": campaign.starts_on.isoformat(),
        "ends_on": campaign.ends_on.isoformat(),
        "status": campaign.status,
    }


@router.patch("/campaigns/{campaign_id}")
def update_campaign(
    campaign_id: UUID,
    changes: CampaignUpdate,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    campaign = db.scalar(
        select(Campaign).where(
            Campaign.id == campaign_id, Campaign.user_id == auth.user.id
        )
    )
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign.status = changes.status
    _audit(db, auth.user, "campaign.updated")
    db.commit()
    return {"id": str(campaign.id), "status": campaign.status}


@router.get("/reviews")
def list_reviews(
    auth: Authenticated, db: Session = Depends(get_db)
) -> list[dict[str, object]]:
    reviews = db.scalars(
        select(Review)
        .where(Review.user_id == auth.user.id)
        .order_by(Review.created_at.desc())
    ).all()
    return [_review_payload(review) for review in reviews]


@router.post("/reviews", status_code=201)
def create_review(
    request: ReviewCreate,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    responses = request.responses.model_dump(exclude_none=True)
    if responses and not _consent_active(db, auth.user.id, "reflection_storage"):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "reflection_consent_required",
                "message": (
                    "Grant reflection_storage consent before saving review responses."
                ),
            },
        )
    review = Review(
        user_id=auth.user.id,
        cadence=request.cadence,
        period_start=request.period_start,
        period_end=request.period_end,
        status=request.status,
        responses=responses,
    )
    db.add(review)
    _audit(db, auth.user, "review.created")
    db.commit()
    db.refresh(review)
    return _review_payload(review)


@router.patch("/reviews/{review_id}")
def update_review(
    review_id: UUID,
    changes: ReviewUpdate,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    review = db.scalar(
        select(Review).where(Review.id == review_id, Review.user_id == auth.user.id)
    )
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")
    if changes.responses is not None:
        responses = changes.responses.model_dump(exclude_none=True)
        if responses and not _consent_active(db, auth.user.id, "reflection_storage"):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "reflection_consent_required",
                    "message": (
                        "Grant reflection_storage consent before saving "
                        "review responses."
                    ),
                },
            )
        review.responses = responses
    if changes.status is not None:
        review.status = changes.status
    _audit(db, auth.user, "review.updated")
    db.commit()
    return _review_payload(review)


def export_lifecycle_data(
    db: Session, user_id: UUID
) -> dict[str, list[dict[str, object]]]:
    """Export account-owned onboarding answers, campaigns, and reviews."""
    campaigns = db.scalars(select(Campaign).where(Campaign.user_id == user_id)).all()
    steps = db.scalars(
        select(OnboardingStep).where(OnboardingStep.user_id == user_id)
    ).all()
    reviews = db.scalars(select(Review).where(Review.user_id == user_id)).all()
    return {
        "campaigns": [
            {
                "id": str(item.id),
                "title": item.title,
                "objective": item.objective,
                "starts_on": item.starts_on.isoformat(),
                "ends_on": item.ends_on.isoformat(),
                "status": item.status,
            }
            for item in campaigns
        ],
        "onboarding_steps": [
            {
                "step": item.step_number,
                "status": item.status,
                "answer": item.answer,
                "updated_at": item.updated_at.isoformat(),
            }
            for item in steps
        ],
        "reviews": [_review_payload(item) for item in reviews],
    }
