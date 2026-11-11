from datetime import date
from uuid import UUID

from sqlalchemy.orm import Session

from liferesets.models import Campaign, User


def _login(client, test_user: dict[str, object]) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": test_user["email"], "password": test_user["password"]},
    )
    assert response.status_code == 200
    client.headers.update({"X-CSRF-Token": client.cookies.get("lr-csrf")})


def _record_reflection_consent(client) -> None:
    response = client.post(
        "/api/v1/consents",
        json={"purpose": "reflection_storage", "granted": True, "policy_version": "v1"},
    )
    assert response.status_code == 201


def test_awakening_is_resumable_and_collects_no_answers(client, test_user) -> None:
    _login(client, test_user)
    initial = client.get("/api/v1/onboarding/awakening").json()
    assert len(initial["steps"]) == 7
    assert initial["completed"] == 0
    assert initial["steps"][5]["status"] == "not_started"
    assert (
        client.patch(
            "/api/v1/onboarding/awakening/6", json={"status": "completed"}
        ).status_code
        == 200
    )
    resumed = client.get("/api/v1/onboarding/awakening").json()
    assert resumed["completed"] == 1
    assert resumed["steps"][5]["status"] == "completed"
    assert db_no_answers(client)


def db_no_answers(client) -> bool:
    result = client.get("/api/v1/onboarding/awakening").json()
    return all(set(step) == {"step", "status"} for step in result["steps"])


def test_campaign_is_90_days_and_owned(client, test_user, db_session: Session) -> None:
    _login(client, test_user)
    payload = {
        "title": "Q1 focus",
        "objective": "Build a steady study routine",
        "starts_on": "2026-01-01",
        "ends_on": "2026-03-31",
    }
    assert (
        client.post(
            "/api/v1/campaigns", json={**payload, "ends_on": "2026-03-30"}
        ).status_code
        == 422
    )
    created = client.post("/api/v1/campaigns", json=payload)
    assert created.status_code == 201, created.text
    campaign = created.json()
    assert campaign["status"] == "active"
    assert len(client.get("/api/v1/campaigns").json()) == 1

    other_id = UUID("00000000-0000-0000-0000-000000000001")
    db_session.add(User(id=other_id, email="other@example.com", password_hash="unused"))
    foreign = Campaign(
        user_id=other_id,
        title="Private",
        objective="Secret",
        starts_on=date(2026, 1, 1),
        ends_on=date(2026, 3, 31),
    )
    db_session.add(foreign)
    db_session.commit()
    assert (
        client.patch(
            f"/api/v1/campaigns/{foreign.id}", json={"status": "paused"}
        ).status_code
        == 404
    )


def test_review_responses_require_current_consent_and_export(client, test_user) -> None:
    _login(client, test_user)
    payload = {
        "cadence": "weekly",
        "period_start": "2026-11-02",
        "period_end": "2026-11-08",
        "responses": {"wins": "Finished a lesson"},
    }
    assert client.post("/api/v1/reviews", json=payload).status_code == 403
    _record_reflection_consent(client)
    created = client.post("/api/v1/reviews", json=payload)
    assert created.status_code == 201, created.text
    review = created.json()
    assert review["responses"]["wins"] == "Finished a lesson"
    assert (
        client.get("/api/v1/export").json()["lifecycle_data"]["reviews"][0]["id"]
        == review["id"]
    )

    withdrawal = client.post(
        "/api/v1/consents",
        json={
            "purpose": "reflection_storage",
            "granted": False,
            "policy_version": "v1",
        },
    )
    assert withdrawal.status_code == 201
    update = client.patch(
        f"/api/v1/reviews/{review['id']}", json={"responses": {"wins": "Changed"}}
    )
    assert update.status_code == 403
    assert (
        client.get("/api/v1/reviews").json()[0]["responses"]["wins"]
        == "Finished a lesson"
    )


def test_review_period_is_validated(client, test_user) -> None:
    _login(client, test_user)
    response = client.post(
        "/api/v1/reviews",
        json={
            "cadence": "monthly",
            "period_start": "2026-12-02",
            "period_end": "2026-12-01",
        },
    )
    assert response.status_code == 422


def test_campaign_onboarding_review_endpoints_require_auth(client) -> None:
    assert client.get("/api/v1/onboarding/awakening").status_code == 401
    assert client.get("/api/v1/campaigns").status_code == 401
    assert client.get("/api/v1/reviews").status_code == 401
