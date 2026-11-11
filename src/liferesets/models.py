"""Identity and privacy data models."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from liferesets.base import Base


def utc_now() -> datetime:
    """Return the current UTC time for application-generated timestamps."""
    return datetime.now(UTC)


class User(Base):
    """A local account with one personal profile."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    profile: Mapped[Profile | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    sessions: Mapped[list[AuthSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    consents: Mapped[list[ConsentRecord]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    audit_events: Mapped[list[AuditEvent]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    goals: Mapped[list[Goal]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    tasks: Mapped[list[Task]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    habits: Mapped[list[Habit]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    evidence: Mapped[list[Evidence]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    campaigns: Mapped[list[Campaign]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    onboarding_steps: Mapped[list[OnboardingStep]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    reviews: Mapped[list[Review]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    daily_plans: Mapped[list[DailyPlan]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    progression_settings: Mapped[ProgressionSettings | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    progression_events: Mapped[list[ProgressionEvent]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    skills: Mapped[list[Skill]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    skill_evidence: Mapped[list[SkillEvidence]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    agent_actions: Mapped[list[AgentAction]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class Profile(Base):
    """User-editable profile details, separate from login credentials."""

    __tablename__ = "profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    display_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    timezone: Mapped[str] = mapped_column(String(100), default="UTC", nullable=False)
    preferences: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=utc_now,
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="profile")


class AuthSession(Base):
    """Revocable session represented by a verifier hash, never a raw token."""

    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[User] = relationship(back_populates="sessions")


class ConsentRecord(Base):
    """Append-only grant or withdrawal record for a named processing purpose."""

    __tablename__ = "consent_records"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    purpose: Mapped[str] = mapped_column(String(80))
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="consents")


class AuditEvent(Base):
    """Minimal account audit event with no request bodies or credential values."""

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    user: Mapped[User | None] = relationship(back_populates="audit_events")


class Goal(Base):
    """A measurable outcome owned by one user and assigned to one domain."""

    __tablename__ = "goals"
    __table_args__ = (
        CheckConstraint(
            "domain IN ('career','fitness','finance','discipline','learning',"
            "'mental_wellness','relationships','lifestyle')",
            name="valid_domain",
        ),
        CheckConstraint("priority BETWEEN 1 AND 5", name="valid_priority"),
        CheckConstraint(
            "status IN ('active','paused','completed','archived')",
            name="valid_goal_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    domain: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="goals")
    metrics: Mapped[list[GoalMetric]] = relationship(
        back_populates="goal", cascade="all, delete-orphan", passive_deletes=True
    )


class GoalMetric(Base):
    """A target and optional baseline for a goal, with an explicit unit."""

    __tablename__ = "goal_metrics"
    __table_args__ = (
        CheckConstraint(
            "source IN ('self_report','imported','verified')",
            name="valid_metric_source",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    goal_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("goals.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    baseline_value: Mapped[Decimal | None] = mapped_column(
        Numeric(16, 4), nullable=True
    )
    target_value: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False)
    current_value: Mapped[Decimal | None] = mapped_column(Numeric(16, 4), nullable=True)
    source: Mapped[str] = mapped_column(
        String(20), default="self_report", nullable=False
    )
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    goal: Mapped[Goal] = relationship(back_populates="metrics")


class Task(Base):
    """A scheduled action or checkpoint associated with an account and goal."""

    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','completed','skipped')", name="valid_task_status"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    goal_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("goals.id", ondelete="SET NULL"), index=True, nullable=True
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="tasks")
    daily_plan_items: Mapped[list[DailyPlanItem]] = relationship(
        back_populates="task", cascade="all, delete-orphan", passive_deletes=True
    )


class Habit(Base):
    """A repeatable routine with a minimum version and recovery path."""

    __tablename__ = "habits"
    __table_args__ = (
        CheckConstraint(
            "frequency IN ('daily','weekly','custom')", name="valid_habit_frequency"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    goal_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("goals.id", ondelete="SET NULL"), index=True, nullable=True
    )
    cue: Mapped[str] = mapped_column(String(160), nullable=False)
    action: Mapped[str] = mapped_column(String(240), nullable=False)
    frequency: Mapped[str] = mapped_column(String(16), nullable=False)
    custom_schedule: Mapped[str | None] = mapped_column(String(160), nullable=True)
    minimum_version: Mapped[str] = mapped_column(String(240), nullable=False)
    recovery_action: Mapped[str] = mapped_column(String(240), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="habits")


class Evidence(Base):
    """Provenance-tagged evidence attached to a goal or task."""

    __tablename__ = "evidence"
    __table_args__ = (
        CheckConstraint(
            "source IN ('self_report','imported','verified')",
            name="valid_evidence_source",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    goal_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("goals.id", ondelete="SET NULL"), index=True, nullable=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="SET NULL"), index=True, nullable=True
    )
    source: Mapped[str] = mapped_column(
        String(20), default="self_report", nullable=False
    )
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    artifact_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="evidence")


class OnboardingStep(Base):
    """Progress and optional consent-gated answer for one Awakening prompt."""

    __tablename__ = "onboarding_steps"
    __table_args__ = (
        UniqueConstraint("user_id", "step_number", name="unique_user_onboarding_step"),
        CheckConstraint("step_number BETWEEN 1 AND 7", name="valid_onboarding_step"),
        CheckConstraint(
            "status IN ('not_started','in_progress','completed','skipped')",
            name="valid_onboarding_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default="not_started", nullable=False
    )
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="onboarding_steps")


class Campaign(Base):
    """A user-owned, time-bounded focus campaign."""

    __tablename__ = "campaigns"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','paused','completed','archived')",
            name="valid_campaign_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    objective: Mapped[str] = mapped_column(String(2000), nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="campaigns")


class Review(Base):
    """Private weekly/monthly reflection with consent-gated response text."""

    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint("cadence IN ('weekly','monthly')", name="valid_review_cadence"),
        CheckConstraint("status IN ('draft','completed')", name="valid_review_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    cadence: Mapped[str] = mapped_column(String(12), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(12), default="draft", nullable=False)
    responses: Mapped[dict[str, str]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="reviews")


class DailyPlan(Base):
    """A capacity-aware plan for one user and local calendar date."""

    __tablename__ = "daily_plans"
    __table_args__ = (
        UniqueConstraint("user_id", "plan_date", name="unique_user_daily_plan"),
        CheckConstraint(
            "capacity_minutes BETWEEN 1 AND 1440", name="valid_plan_capacity"
        ),
        CheckConstraint("energy IN ('low','medium','high')", name="valid_plan_energy"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    plan_date: Mapped[date] = mapped_column(Date, nullable=False)
    capacity_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    energy: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="daily_plans")
    items: Mapped[list[DailyPlanItem]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="DailyPlanItem.position",
    )


class DailyPlanItem(Base):
    """A user-selected task and its status in a dated plan."""

    __tablename__ = "daily_plan_items"
    __table_args__ = (
        UniqueConstraint("plan_id", "task_id", name="unique_task_in_daily_plan"),
        CheckConstraint("position >= 0", name="valid_plan_item_position"),
        CheckConstraint(
            "planned_minutes BETWEEN 1 AND 1440", name="valid_item_minutes"
        ),
        CheckConstraint(
            "status IN ('planned','completed','deferred','dropped')",
            name="valid_daily_item_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("daily_plans.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    planned_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(12), default="planned", nullable=False)
    due_date_at_planning: Mapped[date | None] = mapped_column(Date, nullable=True)
    deferred_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    plan: Mapped[DailyPlan] = relationship(back_populates="items")
    task: Mapped[Task] = relationship(back_populates="daily_plan_items")


class ProgressionSettings(Base):
    """Editable character display and pause state for the optional game layer."""

    __tablename__ = "progression_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    hunter_name: Mapped[str] = mapped_column(
        String(80), default="Hunter", nullable=False
    )
    callsign: Mapped[str | None] = mapped_column(String(80), nullable=True)
    paused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ruleset_version: Mapped[str] = mapped_column(
        String(32), default="starter-1", nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="progression_settings")


class ProgressionEvent(Base):
    """Append-only, versioned XP entry or correction for one account."""

    __tablename__ = "progression_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('task_completed','task_reopened','correction')",
            name="valid_progression_event_type",
        ),
        CheckConstraint("xp_delta BETWEEN -10000 AND 10000", name="valid_xp_delta"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="SET NULL"), index=True, nullable=True
    )
    correction_of_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("progression_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    xp_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    ruleset_version: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(String(240), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="progression_events")


class Skill(Base):
    """User-defined skill with an explicit definition and confidence level."""

    __tablename__ = "skills"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="unique_user_skill_name"),
        CheckConstraint("level BETWEEN 1 AND 10", name="valid_skill_level"),
        CheckConstraint("confidence BETWEEN 0 AND 100", name="valid_skill_confidence"),
        CheckConstraint(
            "domain IS NULL OR domain IN ('career','fitness','finance','discipline',"
            "'learning','mental_wellness','relationships','lifestyle')",
            name="valid_skill_domain",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    domain: Mapped[str | None] = mapped_column(String(32), nullable=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    definition: Mapped[str] = mapped_column(String(500), nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="skills")
    evidence: Mapped[list[SkillEvidence]] = relationship(
        back_populates="skill", cascade="all, delete-orphan", passive_deletes=True
    )


class SkillEvidence(Base):
    """User-recorded, unverified evidence supporting a skill level."""

    __tablename__ = "skill_evidence"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("skills.id", ondelete="CASCADE"), index=True
    )
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    artifact_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    confidence: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="skill_evidence")
    skill: Mapped[Skill] = relationship(back_populates="evidence")


class AgentAction(Base):
    """A proposed local action with its user approval and reversible result."""

    __tablename__ = "agent_actions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('proposed','approved','rejected','undone')",
            name="valid_agent_action_status",
        ),
        CheckConstraint(
            "risk_tier = 'local_reversible'", name="valid_agent_action_risk_tier"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    goal_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("goals.id", ondelete="CASCADE"), index=True
    )
    result_task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    action_type: Mapped[str] = mapped_column(
        String(40), default="create_task", nullable=False
    )
    risk_tier: Mapped[str] = mapped_column(
        String(32), default="local_reversible", nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), default="proposed", nullable=False)
    proposal: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    undone_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[User] = relationship(back_populates="agent_actions")
