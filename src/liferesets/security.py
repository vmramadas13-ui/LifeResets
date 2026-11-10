"""Password hashing and server-side session security."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from pwdlib import PasswordHash
from pwdlib.exceptions import PwdlibError
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.responses import Response

from liferesets.database import get_db
from liferesets.models import AuthSession, User
from liferesets.settings import get_settings

settings = get_settings()
password_hasher = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = password_hasher.hash(secrets.token_urlsafe(32))
SESSION_COOKIE_NAME = (
    "__Host-lr-session" if settings.environment != "development" else "lr-session"
)
CSRF_COOKIE_NAME = "lr-csrf"
COOKIE_SECURE = settings.environment != "development"


@dataclass(frozen=True)
class AuthContext:
    """Authenticated user and the server-side session used for this request."""

    user: User
    session: AuthSession


def hash_password(password: str) -> str:
    """Hash a password with the recommended Argon2id configuration."""
    return password_hasher.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password without propagating malformed hash errors."""
    try:
        return password_hasher.verify(password, stored_hash)
    except PwdlibError:
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(db: Session, user: User) -> tuple[AuthSession, str, str]:
    """Revoke existing sessions and create a fresh opaque session and CSRF token."""
    now = datetime.now(UTC)
    for old_session in db.scalars(
        select(AuthSession).where(
            AuthSession.user_id == user.id,
            AuthSession.revoked_at.is_(None),
        )
    ):
        old_session.revoked_at = now

    session_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    auth_session = AuthSession(
        user_id=user.id,
        token_hash=_token_hash(session_token),
        csrf_token_hash=_token_hash(csrf_token),
        expires_at=now + timedelta(hours=settings.session_ttl_hours),
    )
    db.add(auth_session)
    db.flush()
    return auth_session, session_token, csrf_token


def set_session_cookies(
    response: Response, session_token: str, csrf_token: str
) -> None:
    """Set a host-only, HttpOnly session cookie and a CSRF double-submit cookie."""
    max_age = settings.session_ttl_hours * 60 * 60
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        max_age=max_age,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="strict",
        path="/",
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        max_age=max_age,
        httponly=False,
        secure=COOKIE_SECURE,
        samesite="strict",
        path="/",
    )


def clear_session_cookies(response: Response) -> None:
    """Expire both authentication cookies."""
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        secure=COOKIE_SECURE,
        httponly=True,
        samesite="strict",
        path="/",
    )
    response.delete_cookie(
        key=CSRF_COOKIE_NAME,
        secure=COOKIE_SECURE,
        httponly=False,
        samesite="strict",
        path="/",
    )


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail={
            "code": "authentication_required",
            "message": "Authentication is required.",
        },
    )


def get_authenticated_session(
    request: Request, db: Annotated[Session, Depends(get_db)]
) -> AuthContext:
    """Resolve a valid, unexpired session cookie to its user."""
    raw_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not raw_token or len(raw_token) > 200:
        raise _unauthorized()

    auth_session = db.scalar(
        select(AuthSession).where(AuthSession.token_hash == _token_hash(raw_token))
    )
    now = datetime.now(UTC)
    if auth_session is None or auth_session.revoked_at is not None:
        raise _unauthorized()
    expires_at = auth_session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= now:
        raise _unauthorized()

    user = db.get(User, auth_session.user_id)
    if user is None or not user.is_active:
        raise _unauthorized()
    return AuthContext(user=user, session=auth_session)


def require_csrf(
    request: Request,
    auth: Annotated[AuthContext, Depends(get_authenticated_session)],
) -> AuthContext:
    """Require a session-bound double-submit CSRF token for state changes."""
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME, "")
    header_token = request.headers.get("X-CSRF-Token", "")
    if (
        not cookie_token
        or not header_token
        or not hmac.compare_digest(cookie_token, header_token)
        or not hmac.compare_digest(
            _token_hash(cookie_token), auth.session.csrf_token_hash
        )
    ):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "csrf_validation_failed",
                "message": "CSRF validation failed.",
            },
        )
    return auth


Authenticated = Annotated[AuthContext, Depends(get_authenticated_session)]
AuthenticatedWithCsrf = Annotated[AuthContext, Depends(require_csrf)]
