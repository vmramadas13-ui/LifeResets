"""Authenticated profile, consent, audit, and account data endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from liferesets.database import get_db
from liferesets.domain_data import export_domain_data
from liferesets.lifecycle import export_lifecycle_data
from liferesets.models import AuditEvent, ConsentRecord, Profile, User
from liferesets.security import (
    DUMMY_PASSWORD_HASH,
    Authenticated,
    AuthenticatedWithCsrf,
    clear_session_cookies,
    create_session,
    set_session_cookies,
    verify_password,
)

router = APIRouter(prefix="/api/v1", tags=["identity"])


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    timezone: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("timezone", mode="before")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("Timezone cannot be null")
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("Unknown timezone") from error
        return value


class ConsentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_.-]*$")
    granted: bool
    policy_version: str = Field(min_length=1, max_length=40)


class DeleteAccountInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=1024)
    confirmation: Literal["DELETE MY ACCOUNT"]


def _audit(db: Session, user_id: UUID | None, action: str) -> None:
    db.add(AuditEvent(user_id=user_id, action=action))


def _profile_payload(profile: Profile | None) -> dict[str, object]:
    if profile is None:
        return {
            "display_name": None,
            "timezone": "UTC",
            "preferences": {},
            "updated_at": None,
        }
    return {
        "display_name": profile.display_name,
        "timezone": profile.timezone,
        "preferences": profile.preferences,
        "updated_at": _iso_utc(profile.updated_at),
    }


def _iso_utc(value: datetime) -> str:
    """Serialize database timestamps consistently as UTC with an offset."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _auth_failed() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail={
            "code": "invalid_credentials",
            "message": "Email or password is incorrect.",
        },
    )


@router.post("/auth/login")
def login(
    credentials: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Authenticate and issue a fresh server-side session cookie."""
    normalized_email = str(credentials.email).strip().casefold()
    user = db.scalar(select(User).where(User.email == normalized_email))
    if user is None:
        verify_password(credentials.password, DUMMY_PASSWORD_HASH)
        raise _auth_failed()
    if not user.is_active or not verify_password(
        credentials.password, user.password_hash
    ):
        raise _auth_failed()

    _, raw_session_token, raw_csrf_token = create_session(db, user)
    _audit(db, user.id, "auth.login")
    db.commit()
    set_session_cookies(response, raw_session_token, raw_csrf_token)
    return {"status": "authenticated"}


@router.get("/auth/me")
def current_user(auth: Authenticated) -> dict[str, str]:
    """Return the signed-in account's public identity fields."""
    return {"id": str(auth.user.id), "email": auth.user.email}


@router.post("/auth/logout", status_code=204)
def logout(
    response: Response,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> Response:
    """Revoke the current session and clear its browser cookies."""
    _audit(db, auth.user.id, "auth.logout")
    db.delete(auth.session)
    db.commit()
    clear_session_cookies(response)
    response.status_code = 204
    return response


@router.get("/profile")
def get_profile(
    auth: Authenticated, db: Session = Depends(get_db)
) -> dict[str, object]:
    """Read the signed-in user's profile."""
    profile = db.get(Profile, auth.user.id)
    return _profile_payload(profile)


@router.patch("/profile")
def update_profile(
    changes: ProfileUpdate,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Update only the signed-in user's profile."""
    profile = db.get(Profile, auth.user.id)
    if profile is None:
        profile = Profile(user_id=auth.user.id)
        db.add(profile)
    for field, value in changes.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    profile.updated_at = datetime.now(UTC)
    _audit(db, auth.user.id, "profile.updated")
    db.commit()
    return _profile_payload(profile)


@router.post("/consents", status_code=201)
def record_consent(
    consent: ConsentInput,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Append a consent grant or withdrawal for the signed-in user."""
    record = ConsentRecord(
        user_id=auth.user.id,
        purpose=consent.purpose,
        granted=consent.granted,
        policy_version=consent.policy_version,
    )
    db.add(record)
    _audit(db, auth.user.id, "consent.recorded")
    db.commit()
    return {
        "id": str(record.id),
        "purpose": record.purpose,
        "granted": record.granted,
        "policy_version": record.policy_version,
        "created_at": _iso_utc(record.created_at),
    }


@router.get("/consents")
def list_consents(
    auth: Authenticated, db: Session = Depends(get_db)
) -> list[dict[str, object]]:
    """List consent records for the signed-in user."""
    records = db.scalars(
        select(ConsentRecord)
        .where(ConsentRecord.user_id == auth.user.id)
        .order_by(ConsentRecord.created_at, ConsentRecord.id)
    ).all()
    return [
        {
            "id": str(record.id),
            "purpose": record.purpose,
            "granted": record.granted,
            "policy_version": record.policy_version,
            "created_at": _iso_utc(record.created_at),
        }
        for record in records
    ]


@router.get("/audit")
def list_audit_events(
    auth: Authenticated, db: Session = Depends(get_db)
) -> list[dict[str, str]]:
    """List minimal account audit events without credential or request data."""
    events = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.user_id == auth.user.id)
        .order_by(AuditEvent.created_at, AuditEvent.id)
    ).all()
    return [
        {
            "id": str(event.id),
            "action": event.action,
            "created_at": _iso_utc(event.created_at),
        }
        for event in events
    ]


@router.get("/export")
def export_account_data(
    auth: Authenticated, db: Session = Depends(get_db)
) -> dict[str, object]:
    """Export inspectable personal data without password hashes or session tokens."""
    _audit(db, auth.user.id, "data.exported")
    db.commit()
    profile = db.get(Profile, auth.user.id)
    consents = db.scalars(
        select(ConsentRecord)
        .where(ConsentRecord.user_id == auth.user.id)
        .order_by(ConsentRecord.created_at, ConsentRecord.id)
    ).all()
    events = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.user_id == auth.user.id)
        .order_by(AuditEvent.created_at, AuditEvent.id)
    ).all()
    return {
        "account": {
            "id": str(auth.user.id),
            "email": auth.user.email,
            "created_at": _iso_utc(auth.user.created_at),
        },
        "profile": _profile_payload(profile),
        "consents": [
            {
                "id": str(record.id),
                "purpose": record.purpose,
                "granted": record.granted,
                "policy_version": record.policy_version,
                "created_at": _iso_utc(record.created_at),
            }
            for record in consents
        ],
        "audit": [
            {
                "id": str(event.id),
                "action": event.action,
                "created_at": _iso_utc(event.created_at),
            }
            for event in events
        ],
        "domain_data": export_domain_data(db, auth.user.id),
        "lifecycle_data": export_lifecycle_data(db, auth.user.id),
    }


@router.delete("/account", status_code=204)
def delete_account(
    request: DeleteAccountInput,
    response: Response,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> Response:
    """Hard-delete the account after CSRF, password, and phrase confirmation."""
    if not verify_password(request.current_password, auth.user.password_hash):
        raise HTTPException(
            status_code=401,
            detail={
                "code": "reauthentication_failed",
                "message": "Password confirmation failed.",
            },
        )

    deleted_user = auth.user
    db.add(AuditEvent(user_id=None, action="account.deleted"))
    db.delete(deleted_user)
    db.commit()
    clear_session_cookies(response)
    response.status_code = 204
    return response
