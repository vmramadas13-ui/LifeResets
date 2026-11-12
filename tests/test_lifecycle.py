from datetime import date
from uuid import UUID

from sqlalchemy.orm import Session

from liferesets.models import Campaign, Review, User


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


def _record_awakening_consent(client, granted: bool = True) -> None:
    response = client.post(
        "/api/v1/consents",
        json={
            "purpose": "awakening_storage",
            "granted": granted,
            "policy_version": "v1",
        },
    )
    assert response.status_code == 201


def test_awakening_guides_seven_prompts_and_requires_consent_for_answers(
    client, test_user
) -> None:
    _login(client, test_user)
    initial = client.get("/api/v1/onboarding/awakening").json()
    assert len(initial["steps"]) == 7
    assert initial["completed"] == 0
    assert initial["steps"][0]["day"] == 1
    assert initial["steps"][0]["title"] == "Choose your focus"
    assert initial["steps"][0]["prompt"]
    assert initial["steps"][5]["status"] == "not_started"
    assert initial["storage_consent"] is False
    denied = client.patch(
        "/api/v1/onboarding/awakening/1",
        json={"status": "completed", "answer": "A test reflection"},
    )
    assert denied.status_code == 403

    # Progress markers remain available without storing an answer.
    assert (
        client.patch(
            "/api/v1/onboarding/awakening/6", json={"status": "completed"}
        ).status_code
        == 200
    )
    _record_awakening_consent(client)
    saved = client.patch(
        "/api/v1/onboarding/awakening/1",
        json={"status": "completed", "answer": "A test reflection"},
    )
    assert saved.status_code == 200
    draft = client.patch(
        "/api/v1/onboarding/awakening/3",
        json={"status": "in_progress", "answer": "A saved draft"},
    )
    assert draft.status_code == 200
    resumed = client.get("/api/v1/onboarding/awakening").json()
    assert resumed["completed"] == 2
    assert resumed["steps"][5]["status"] == "completed"
    assert resumed["steps"][0]["answer"] == "A test reflection"
    assert resumed["steps"][2]["status"] == "in_progress"
    assert resumed["steps"][2]["answer"] == "A saved draft"
    assert resumed["storage_consent"] is True
    exported = client.get("/api/v1/export").json()["lifecycle_data"]["onboarding_steps"]
    assert {item["answer"] for item in exported} == {
        None,
        "A test reflection",
        "A saved draft",
    }


def test_awakening_withdrawal_blocks_answer_updates_and_delete_clears_answers(
    client, test_user
) -> None:
    _login(client, test_user)
    _record_awakening_consent(client)
    assert (
        client.patch(
            "/api/v1/onboarding/awakening/2",
            json={"status": "completed", "answer": "A private test note"},
        ).status_code
        == 200
    )
    _record_awakening_consent(client, granted=False)
    blocked = client.patch(
        "/api/v1/onboarding/awakening/2",
        json={"status": "completed", "answer": "Changed after withdrawal"},
    )
    assert blocked.status_code == 403
    assert (
        client.get("/api/v1/onboarding/awakening").json()["steps"][1]["answer"]
        == "A private test note"
    )
    deleted = client.delete("/api/v1/onboarding/awakening/answers")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted_answers": 1}
    assert (
        client.get("/api/v1/onboarding/awakening").json()["steps"][1]["answer"] is None
    )


def test_awakening_answer_length_and_step_bounds(client, test_user) -> None:
    _login(client, test_user)
    invalid_step = client.patch(
        "/api/v1/onboarding/awakening/0", json={"status": "completed"}
    )
    assert invalid_step.status_code == 404
    too_long = client.patch(
        "/api/v1/onboarding/awakening/1",
        json={"status": "completed", "answer": "x" * 1201},
    )
    assert too_long.status_code == 422


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
    foreign_review = Review(
        user_id=other_id,
        cadence="weekly",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 7),
        responses={"wins": "Private reflection"},
    )
    db_session.add_all([foreign, foreign_review])
    db_session.commit()
    assert (
        client.patch(
            f"/api/v1/campaigns/{foreign.id}", json={"status": "paused"}
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/api/v1/reviews/{foreign_review.id}/responses").status_code
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
    assert review["prompts"]["wins"] == "What went well or felt meaningful this week?"
    assert set(review["prompts"]) == {"wins", "blockers", "changes", "next_step"}
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
    deleted = client.delete(f"/api/v1/reviews/{review['id']}/responses")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted_fields": 1}
    assert client.get("/api/v1/reviews").json()[0]["responses"] == {}


def test_monthly_review_has_its_own_guided_prompts(client, test_user) -> None:
    _login(client, test_user)
    created = client.post(
        "/api/v1/reviews",
        json={
            "cadence": "monthly",
            "period_start": "2026-10-01",
            "period_end": "2026-10-31",
        },
    )
    assert created.status_code == 201
    assert (
        created.json()["prompts"]["wins"]
        == "What progress or moments mattered this month?"
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
