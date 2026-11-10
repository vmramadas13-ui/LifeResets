import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from liferesets.models import (
    AuditEvent,
    AuthSession,
    ConsentRecord,
    Profile,
    User,
)


def _login(client, test_user: dict[str, object]) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": str(test_user["email"]).upper(),
            "password": test_user["password"],
        },
    )
    assert response.status_code == 200
    assert response.json() == {"status": "authenticated"}
    assert client.cookies.get("lr-session")
    assert client.cookies.get("lr-session") not in response.text
    csrf_token = client.cookies.get("lr-csrf")
    assert csrf_token
    client.headers.update({"X-CSRF-Token": csrf_token})


def test_protected_endpoints_require_authentication(client) -> None:
    paths = [
        "/api/v1/auth/me",
        "/api/v1/profile",
        "/api/v1/consents",
        "/api/v1/audit",
        "/api/v1/export",
    ]

    for path in paths:
        response = client.get(path)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "authentication_required"

    mutations = [
        ("POST", "/api/v1/auth/logout", None),
        ("PATCH", "/api/v1/profile", {"display_name": "No access"}),
        (
            "POST",
            "/api/v1/consents",
            {"purpose": "ai_processing", "granted": True, "policy_version": "v1"},
        ),
        (
            "DELETE",
            "/api/v1/account",
            {"current_password": "irrelevant", "confirmation": "DELETE MY ACCOUNT"},
        ),
    ]
    for method, path, body in mutations:
        response = client.request(method, path, json=body)
        assert response.status_code == 401


def test_login_issues_hashed_session_and_rotates_old_sessions(
    client, db_session: Session, test_user: dict[str, object]
) -> None:
    _login(client, test_user)
    first_cookie = client.cookies.get("lr-session")
    first_csrf = client.cookies.get("lr-csrf")
    second_login = client.post(
        "/api/v1/auth/login",
        json={"email": test_user["email"], "password": test_user["password"]},
    )
    second_cookie = client.cookies.get("lr-session")
    assert second_login.status_code == 200
    assert first_cookie != second_cookie
    assert first_csrf != client.cookies.get("lr-csrf")
    assert any(
        header.startswith("lr-session=")
        and "httponly" in header.lower()
        and "samesite=strict" in header.lower()
        for header in second_login.headers.get_list("set-cookie")
    )

    sessions = db_session.scalars(
        select(AuthSession).where(AuthSession.user_id == test_user["id"])
    ).all()
    assert len(sessions) == 2
    assert all(
        session.token_hash not in {first_cookie, second_cookie} for session in sessions
    )
    assert hashlib.sha256(second_cookie.encode()).hexdigest() in {
        session.token_hash for session in sessions
    }
    assert hashlib.sha256(client.cookies.get("lr-csrf").encode()).hexdigest() in {
        session.csrf_token_hash for session in sessions
    }
    assert sum(session.revoked_at is not None for session in sessions) == 1
    assert client.get("/api/v1/auth/me").status_code == 200


def test_failed_login_does_not_disclose_account_existence(client) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "missing@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json()["error"] == {
        "code": "invalid_credentials",
        "message": "Email or password is incorrect.",
    }


def test_logout_revokes_the_current_session(
    client, test_user: dict[str, object]
) -> None:
    _login(client, test_user)

    response = client.post("/api/v1/auth/logout")

    assert response.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_profile_updates_are_owned_and_require_csrf(
    client, db_session: Session, test_user: dict[str, object]
) -> None:
    _login(client, test_user)
    client.headers.pop("X-CSRF-Token")
    response = client.patch("/api/v1/profile", json={"display_name": "Changed"})
    assert response.status_code == 403

    client.headers.update({"X-CSRF-Token": client.cookies.get("lr-csrf")})
    response = client.patch(
        "/api/v1/profile",
        json={"display_name": "Groot", "timezone": "Asia/Kolkata"},
    )
    assert response.status_code == 200
    assert response.json()["display_name"] == "Groot"

    null_timezone = client.patch("/api/v1/profile", json={"timezone": None})
    assert null_timezone.status_code == 422

    forged = client.patch(
        "/api/v1/profile",
        json={"display_name": "Other", "user_id": "another-user"},
    )
    assert forged.status_code == 422
    db_session.expire_all()
    profile = db_session.get(Profile, test_user["id"])
    assert profile is not None and profile.display_name == "Groot"


def test_consent_records_are_append_only_and_account_scoped(
    client, db_session: Session, test_user: dict[str, object]
) -> None:
    _login(client, test_user)
    other_user = User(email="other@example.com", password_hash="not-used-in-this-test")
    other_user.consents.append(
        ConsentRecord(
            purpose="calendar_sync",
            granted=True,
            policy_version="v1",
        )
    )
    db_session.add(other_user)
    db_session.commit()

    for granted in (True, False):
        response = client.post(
            "/api/v1/consents",
            json={
                "purpose": "ai_processing",
                "granted": granted,
                "policy_version": "v1",
            },
        )
        assert response.status_code == 201

    response = client.get("/api/v1/consents")
    assert response.status_code == 200
    assert [record["granted"] for record in response.json()] == [True, False]
    assert all(record["purpose"] == "ai_processing" for record in response.json())


def test_export_includes_user_data_but_excludes_credentials(
    client, test_user: dict[str, object]
) -> None:
    _login(client, test_user)
    client.patch("/api/v1/profile", json={"display_name": "Groot"})
    client.post(
        "/api/v1/consents",
        json={"purpose": "ai_processing", "granted": True, "policy_version": "v1"},
    )

    response = client.get("/api/v1/export")

    assert response.status_code == 200
    payload = response.json()
    assert payload["account"]["email"] == test_user["email"]
    assert payload["account"]["created_at"].endswith("+00:00")
    assert payload["profile"]["display_name"] == "Groot"
    assert payload["profile"]["updated_at"].endswith("+00:00")
    assert payload["consents"][0]["purpose"] == "ai_processing"
    assert payload["consents"][0]["id"]
    assert "data.exported" in [event["action"] for event in payload["audit"]]
    assert "password_hash" not in response.text
    assert "token_hash" not in response.text
    assert client.cookies.get("lr-session") not in response.text


def test_account_deletion_requires_password_and_confirmation(
    client, db_session: Session, test_user: dict[str, object]
) -> None:
    _login(client, test_user)
    other_user = User(email="other@example.com", password_hash="not-used-in-this-test")
    other_user.profile = Profile(display_name="Other", timezone="UTC")
    other_user.consents.append(
        ConsentRecord(purpose="calendar_sync", granted=True, policy_version="v1")
    )
    db_session.add(other_user)
    db_session.commit()
    csrf_token = client.cookies.get("lr-csrf")

    wrong_password = client.request(
        "DELETE",
        "/api/v1/account",
        headers={"X-CSRF-Token": csrf_token},
        json={"current_password": "incorrect", "confirmation": "DELETE MY ACCOUNT"},
    )
    assert wrong_password.status_code == 401
    assert db_session.scalar(select(func.count()).select_from(User)) == 2

    deleted = client.request(
        "DELETE",
        "/api/v1/account",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "current_password": test_user["password"],
            "confirmation": "DELETE MY ACCOUNT",
        },
    )
    assert deleted.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401

    db_session.expire_all()
    assert db_session.scalar(select(func.count()).select_from(User)) == 1
    assert db_session.scalar(select(func.count()).select_from(Profile)) == 1
    assert db_session.scalar(select(func.count()).select_from(ConsentRecord)) == 1
    deletion_event = db_session.scalar(
        select(AuditEvent).where(AuditEvent.action == "account.deleted")
    )
    assert deletion_event is not None
    assert deletion_event.user_id is None
