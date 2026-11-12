"""Resumable onboarding, 90-day campaigns, and consent-aware reviews."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from liferesets.database import get_db
from liferesets.domain_data import DomainCode
from liferesets.models import (
    AuditEvent,
    AwakeningBaseline,
    AwakeningBaselineGoalLink,
    Campaign,
    ConsentRecord,
    Goal,
    OnboardingStep,
    Review,
    ReviewFollowUp,
    Task,
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


class AwakeningBaselineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: DomainCode
    metric_name: str = Field(min_length=1, max_length=120)
    status: Literal["recorded", "unknown"]
    value: Decimal | None = Field(
        default=None, max_digits=16, decimal_places=4, allow_inf_nan=False
    )
    unit: str | None = Field(default=None, max_length=40)
    measured_on: date | None = None
    confidence: int = Field(default=50, ge=0, le=100)

    @field_validator("metric_name")
    @classmethod
    def trim_metric_name(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("metric_name cannot be blank")
        return trimmed

    @field_validator("unit")
    @classmethod
    def trim_unit(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None

    @model_validator(mode="after")
    def valid_value_for_status(self) -> AwakeningBaselineInput:
        if self.status == "recorded" and (self.value is None or self.unit is None):
            raise ValueError("A numeric baseline requires both a value and a unit")
        if self.status == "unknown" and self.value is not None:
            raise ValueError("An unknown baseline cannot include a numeric value")
        return self


class AwakeningBaselineGoalLinkInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goal_id: UUID


AWAKENING_PROMPTS = (
    {
        "focus": "Profile, priorities, and consent",
        "title": "Choose your focus",
        "prompt": (
            "Which parts of life matter most to you right now, and what would you "
            "like this reset to help you change? Choose what to save using the "
            "separate consent controls; you can skip this prompt."
        ),
    },
    {
        "focus": "Life map and current reality",
        "title": "Map where you are now",
        "prompt": (
            "Across your life areas, what is going well, what feels difficult, and "
            "where are you unsure? You can record a starting point or mark it "
            "unknown; no number is required."
        ),
    },
    {
        "focus": "Goals, horizons, and milestones",
        "title": "Describe what you want to change",
        "prompt": (
            "What longer-term outcome would matter to you, and what milestone could "
            "show that you are moving toward it? Nothing is added as a goal until "
            "you save it in Goals."
        ),
    },
    {
        "focus": "Capacity, constraints, and boundaries",
        "title": "Make room for a realistic change",
        "prompt": (
            "What time, energy, responsibilities, or boundaries should your plan "
            "respect? What size of first step feels sustainable?"
        ),
    },
    {
        "focus": "Health and routines · optional",
        "title": "Review health and routine starting points",
        "prompt": (
            "If you want to, consider fitness, sleep, wellbeing, or routines. What "
            "would be useful to understand or improve? This is optional and is not "
            "a diagnosis or a health score."
        ),
    },
    {
        "focus": "Finance, relationships, and lifestyle · optional",
        "title": "Review other life areas",
        "prompt": (
            "If you want to, consider finances, relationships, and lifestyle. What "
            "commitments or support would make change easier? Do not enter passwords "
            "or access codes."
        ),
    },
    {
        "focus": "First 90-day campaign and first week",
        "title": "Choose a first-week experiment",
        "prompt": (
            "What outcome would you like to work toward over 90 days, what is one "
            "small first-week action, and when would you review it? Choose one "
            "low-risk action or observation that could test an assumption. Nothing "
            "is added to a campaign or daily plan until you save it there."
        ),
    },
)

REVIEW_PROMPTS: dict[str, dict[str, str]] = {
    "weekly": {
        "wins": "What went well or felt meaningful this week?",
        "blockers": "What made your plans harder?",
        "changes": "What would you adjust next week?",
        "next_step": "What is one small next step?",
    },
    "monthly": {
        "wins": "What progress or moments mattered this month?",
        "blockers": "What made progress harder this month?",
        "changes": "What would you like to change next month?",
        "next_step": "What is one focus for next month?",
    },
}


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


class ReviewCarryForwardInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goal_id: UUID | None = None


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
        "prompts": REVIEW_PROMPTS[review.cadence],
        "follow_up_task_id": (
            str(review.follow_up.task_id) if review.follow_up is not None else None
        ),
    }


def _baseline_payload(item: AwakeningBaseline) -> dict[str, object]:
    goal_link = item.goal_link
    return {
        "id": str(item.id),
        "domain": item.domain,
        "metric_name": item.metric_name,
        "status": item.status,
        "value": str(item.value) if item.value is not None else None,
        "unit": item.unit,
        "measured_on": item.measured_on.isoformat() if item.measured_on else None,
        "confidence": item.confidence,
        "recorded_at": item.recorded_at.isoformat(),
        "goal_id": str(goal_link.goal_id) if goal_link else None,
        "goal_title": goal_link.goal.title if goal_link else None,
        "linked_at": goal_link.linked_at.isoformat() if goal_link else None,
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
    baselines = db.scalars(
        select(AwakeningBaseline)
        .where(AwakeningBaseline.user_id == auth.user.id)
        .options(
            selectinload(AwakeningBaseline.goal_link).selectinload(
                AwakeningBaselineGoalLink.goal
            )
        )
        .order_by(AwakeningBaseline.recorded_at, AwakeningBaseline.id)
    ).all()
    steps = [
        {
            "step": number,
            "day": number,
            "focus": prompt["focus"],
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
        "baseline_storage_consent": _consent_active(
            db, auth.user.id, "assessment_baseline_storage"
        ),
        "baselines": [_baseline_payload(item) for item in baselines],
    }


@router.post("/onboarding/awakening/baselines", status_code=201)
def create_awakening_baseline(
    request: AwakeningBaselineInput,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Append an explicitly consented numeric baseline or unknown marker."""
    if not _consent_active(db, auth.user.id, "assessment_baseline_storage"):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "baseline_consent_required",
                "message": (
                    "Grant assessment_baseline_storage consent before saving baselines."
                ),
            },
        )
    baseline = AwakeningBaseline(
        user_id=auth.user.id,
        domain=request.domain,
        metric_name=request.metric_name,
        status=request.status,
        value=request.value,
        unit=request.unit,
        measured_on=request.measured_on,
        confidence=request.confidence,
    )
    db.add(baseline)
    _audit(db, auth.user, "onboarding.baseline_recorded")
    db.commit()
    db.refresh(baseline)
    return _baseline_payload(baseline)


@router.delete("/onboarding/awakening/baselines/{baseline_id}")
def delete_awakening_baseline(
    baseline_id: UUID,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Delete one baseline history entry owned by the signed-in account."""
    baseline = db.scalar(
        select(AwakeningBaseline).where(
            AwakeningBaseline.id == baseline_id,
            AwakeningBaseline.user_id == auth.user.id,
        )
    )
    if baseline is None:
        raise HTTPException(status_code=404, detail="Baseline not found")
    db.delete(baseline)
    _audit(db, auth.user, "onboarding.baseline_deleted")
    db.commit()
    return {"status": "deleted"}


@router.post("/onboarding/awakening/baselines/{baseline_id}/goal-link")
def link_awakening_baseline_to_goal(
    baseline_id: UUID,
    request: AwakeningBaselineGoalLinkInput,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Attach an existing starting point to a same-area goal after user choice."""
    baseline = db.scalar(
        select(AwakeningBaseline)
        .where(
            AwakeningBaseline.id == baseline_id,
            AwakeningBaseline.user_id == auth.user.id,
        )
        .options(
            selectinload(AwakeningBaseline.goal_link).selectinload(
                AwakeningBaselineGoalLink.goal
            )
        )
    )
    if baseline is None:
        raise HTTPException(status_code=404, detail="Baseline not found")
    if baseline.goal_link is not None:
        if baseline.goal_link.goal_id == request.goal_id:
            return {
                "created": False,
                "baseline": _baseline_payload(baseline),
            }
        raise HTTPException(
            status_code=409,
            detail={
                "code": "baseline_already_linked",
                "message": "Unlink this starting point before choosing another goal.",
            },
        )
    if not _consent_active(db, auth.user.id, "assessment_baseline_storage"):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "baseline_consent_required",
                "message": (
                    "Grant assessment_baseline_storage consent before linking "
                    "a starting point."
                ),
            },
        )
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
    if goal.domain != baseline.domain:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "baseline_goal_domain_mismatch",
                "message": "Choose an active goal in the same life area.",
            },
        )
    link = AwakeningBaselineGoalLink(baseline=baseline, goal=goal)
    db.add(link)
    _audit(db, auth.user, "onboarding.baseline_linked_to_goal")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(AwakeningBaselineGoalLink)
            .where(AwakeningBaselineGoalLink.baseline_id == baseline_id)
            .options(selectinload(AwakeningBaselineGoalLink.goal))
        )
        if existing is None:
            raise
        if existing.goal_id != request.goal_id:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "baseline_already_linked",
                    "message": (
                        "Unlink this starting point before choosing another goal."
                    ),
                },
            )
        baseline.goal_link = existing
        return {
            "created": False,
            "baseline": _baseline_payload(baseline),
        }
    db.refresh(link)
    return {"created": True, "baseline": _baseline_payload(baseline)}


@router.delete("/onboarding/awakening/baselines/{baseline_id}/goal-link")
def unlink_awakening_baseline_from_goal(
    baseline_id: UUID,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    """Remove only the association; keep the starting point and goal records."""
    baseline = db.scalar(
        select(AwakeningBaseline)
        .where(
            AwakeningBaseline.id == baseline_id,
            AwakeningBaseline.user_id == auth.user.id,
        )
        .options(selectinload(AwakeningBaseline.goal_link))
    )
    if baseline is None:
        raise HTTPException(status_code=404, detail="Baseline not found")
    if baseline.goal_link is None:
        return {"unlinked": False}
    db.delete(baseline.goal_link)
    _audit(db, auth.user, "onboarding.baseline_unlinked_from_goal")
    db.commit()
    return {"unlinked": True}


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
        .options(selectinload(Review.follow_up).selectinload(ReviewFollowUp.task))
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


@router.post("/reviews/{review_id}/carry-forward")
def carry_forward_review_next_step(
    review_id: UUID,
    request: ReviewCarryForwardInput,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Create at most one user-approved task from a completed review's next step."""
    review = db.scalar(
        select(Review)
        .where(Review.id == review_id, Review.user_id == auth.user.id)
        .options(selectinload(Review.follow_up).selectinload(ReviewFollowUp.task))
    )
    if review is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "resource_not_found",
                "message": "The requested resource was not found.",
            },
        )

    if review.follow_up is not None:
        task = review.follow_up.task
        return {
            "created": False,
            "task": {
                "id": str(task.id),
                "title": task.title,
                "goal_id": str(task.goal_id) if task.goal_id else None,
            },
        }

    if review.status != "completed":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "review_not_completed",
                "message": "Complete the review before carrying its next step forward.",
            },
        )
    next_step = (review.responses.get("next_step") or "").strip()
    if not next_step:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "review_next_step_required",
                "message": "Add a next step to the review before carrying it forward.",
            },
        )
    if (
        request.goal_id is not None
        and db.scalar(
            select(Goal.id).where(
                Goal.id == request.goal_id,
                Goal.user_id == auth.user.id,
                Goal.status == "active",
            )
        )
        is None
    ):
        raise HTTPException(
            status_code=404,
            detail={
                "code": "resource_not_found",
                "message": "The requested resource was not found.",
            },
        )

    task = Task(
        user_id=auth.user.id,
        goal_id=request.goal_id,
        title=next_step[:160].strip(),
        description=next_step if len(next_step) > 160 else None,
    )
    follow_up = ReviewFollowUp(review=review, task=task)
    db.add(follow_up)
    _audit(db, auth.user, "review.next_step_carried_forward")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(ReviewFollowUp)
            .where(ReviewFollowUp.review_id == review_id)
            .options(selectinload(ReviewFollowUp.task))
        )
        if existing is None:
            raise
        task = existing.task
        return {
            "created": False,
            "task": {
                "id": str(task.id),
                "title": task.title,
                "goal_id": str(task.goal_id) if task.goal_id else None,
            },
        }
    db.refresh(task)
    return {
        "created": True,
        "task": {
            "id": str(task.id),
            "title": task.title,
            "goal_id": str(task.goal_id) if task.goal_id else None,
        },
    }


@router.delete("/reviews/{review_id}/responses")
def delete_review_responses(
    review_id: UUID,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, int]:
    """Delete saved reflection text while keeping the review record."""
    review = db.scalar(
        select(Review).where(Review.id == review_id, Review.user_id == auth.user.id)
    )
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")
    deleted_fields = len(review.responses)
    review.responses = {}
    _audit(db, auth.user, "review.responses_deleted")
    db.commit()
    return {"deleted_fields": deleted_fields}


def export_lifecycle_data(
    db: Session, user_id: UUID
) -> dict[str, list[dict[str, object]]]:
    """Export account-owned onboarding answers, campaigns, and reviews."""
    campaigns = db.scalars(select(Campaign).where(Campaign.user_id == user_id)).all()
    steps = db.scalars(
        select(OnboardingStep).where(OnboardingStep.user_id == user_id)
    ).all()
    reviews = db.scalars(
        select(Review)
        .where(Review.user_id == user_id)
        .options(selectinload(Review.follow_up).selectinload(ReviewFollowUp.task))
    ).all()
    baselines = db.scalars(
        select(AwakeningBaseline)
        .where(AwakeningBaseline.user_id == user_id)
        .options(
            selectinload(AwakeningBaseline.goal_link).selectinload(
                AwakeningBaselineGoalLink.goal
            )
        )
        .order_by(AwakeningBaseline.recorded_at, AwakeningBaseline.id)
    ).all()
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
        "awakening_baselines": [_baseline_payload(item) for item in baselines],
        "reviews": [_review_payload(item) for item in reviews],
    }
