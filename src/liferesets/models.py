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
    """Progress marker for a resumable seven-part Awakening, with no answers."""

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
