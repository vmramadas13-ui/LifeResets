from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from liferesets.models import AwakeningBaseline, Campaign, Review, User


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


def _record_baseline_consent(client, granted: bool = True) -> None:
    response = client.post(
        "/api/v1/consents",
        json={
            "purpose": "assessment_baseline_storage",
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


def test_awakening_baselines_are_consent_gated_explicit_and_append_only(
    client, test_user
) -> None:
    _login(client, test_user)
    initial = client.get("/api/v1/onboarding/awakening").json()
    assert initial["baseline_storage_consent"] is False
    assert initial["baselines"] == []
    denied = client.post(
        "/api/v1/onboarding/awakening/baselines",
        json={
            "domain": "learning",
            "metric_name": "Study hours",
            "status": "recorded",
            "value": 3,
            "unit": "hours",
        },
    )
    assert denied.status_code == 403

    _record_baseline_consent(client)
    first = client.post(
        "/api/v1/onboarding/awakening/baselines",
        json={
            "domain": "learning",
            "metric_name": "Weekly study hours",
            "status": "recorded",
            "value": 3,
            "unit": "hours",
            "measured_on": "2026-11-10",
            "confidence": 60,
        },
    )
    assert first.status_code == 201, first.text
    revised = client.post(
        "/api/v1/onboarding/awakening/baselines",
        json={
            "domain": "learning",
            "metric_name": "Weekly study hours",
            "status": "recorded",
            "value": 4,
            "unit": "hours",
            "confidence": 75,
        },
    )
    assert revised.status_code == 201, revised.text
    unknown = client.post(
        "/api/v1/onboarding/awakening/baselines",
        json={
            "domain": "finance",
            "metric_name": "Overall baseline",
            "status": "unknown",
            "confidence": 50,
        },
    )
    assert unknown.status_code == 201, unknown.text
    entries = client.get("/api/v1/onboarding/awakening").json()["baselines"]
    assert [item["value"] for item in entries[:2]] == ["3.0000", "4.0000"]
    assert entries[0]["recorded_at"] < entries[1]["recorded_at"]
    assert entries[2]["status"] == "unknown"
    assert entries[2]["value"] is None
    exported = client.get("/api/v1/export").json()["lifecycle_data"][
        "awakening_baselines"
    ]
    assert len(exported) == 3

    _record_baseline_consent(client, granted=False)
    blocked = client.post(
        "/api/v1/onboarding/awakening/baselines",
        json={
            "domain": "learning",
            "metric_name": "Weekly study hours",
            "status": "recorded",
            "value": 5,
            "unit": "hours",
        },
    )
    assert blocked.status_code == 403
    deleted = client.delete(
        f"/api/v1/onboarding/awakening/baselines/{first.json()['id']}"
    )
    assert deleted.status_code == 200
    assert len(client.get("/api/v1/onboarding/awakening").json()["baselines"]) == 2


def test_awakening_baseline_requires_value_and_unit_for_recorded_entries(
    client, test_user
) -> None:
    _login(client, test_user)
    _record_baseline_consent(client)
    missing = client.post(
        "/api/v1/onboarding/awakening/baselines",
        json={"domain": "fitness", "metric_name": "Activity", "status": "recorded"},
    )
    assert missing.status_code == 422
    value_on_unknown = client.post(
        "/api/v1/onboarding/awakening/baselines",
        json={
            "domain": "finance",
            "metric_name": "Overall baseline",
            "status": "unknown",
            "value": 10,
        },
    )
    assert value_on_unknown.status_code == 422


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
    foreign_baseline = AwakeningBaseline(
        user_id=other_id,
        domain="fitness",
        metric_name="Private measure",
        status="recorded",
        value=Decimal("2"),
        unit="sessions",
        confidence=50,
    )
    db_session.add_all([foreign, foreign_review, foreign_baseline])
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
    assert (
        client.post(
            f"/api/v1/reviews/{foreign_review.id}/carry-forward", json={}
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/api/v1/onboarding/awakening/baselines/{foreign_baseline.id}"
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


def test_completed_review_next_step_creates_one_user_selected_task(
    client, test_user
) -> None:
    _login(client, test_user)
    _record_reflection_consent(client)
    goal = client.post(
        "/api/v1/goals", json={"domain": "learning", "title": "Study"}
    ).json()
    next_step = "Practice a small lesson and write what I learned. " * 8
    review_response = client.post(
        "/api/v1/reviews",
        json={
            "cadence": "weekly",
            "period_start": "2026-11-02",
            "period_end": "2026-11-08",
            "status": "completed",
            "responses": {"next_step": next_step},
        },
    )
    assert review_response.status_code == 201, review_response.text
    review = review_response.json()
    assert review["follow_up_task_id"] is None

    draft = client.post(
        "/api/v1/reviews",
        json={
            "cadence": "monthly",
            "period_start": "2026-10-01",
            "period_end": "2026-10-31",
            "responses": {"next_step": "Prepare one practice exercise"},
        },
    ).json()
    draft_carry = client.post(f"/api/v1/reviews/{draft['id']}/carry-forward", json={})
    assert draft_carry.status_code == 409
    no_next_step = client.post(
        "/api/v1/reviews",
        json={
            "cadence": "weekly",
            "period_start": "2026-10-26",
            "period_end": "2026-11-01",
            "status": "completed",
        },
    ).json()
    missing_step = client.post(
        f"/api/v1/reviews/{no_next_step['id']}/carry-forward", json={}
    )
    assert missing_step.status_code == 422

    carry = client.post(
        f"/api/v1/reviews/{review['id']}/carry-forward",
        json={"goal_id": goal["id"]},
    )
    assert carry.status_code == 200, carry.text
    assert carry.json()["created"] is True
    task = carry.json()["task"]
    assert task["goal_id"] == goal["id"]
    assert len(task["title"]) <= 160
    tasks = client.get("/api/v1/tasks").json()
    assert len(tasks) == 1
    assert tasks[0]["description"] == next_step.strip()
    today_plan = client.get(f"/api/v1/daily-plans/{date.today().isoformat()}")
    assert today_plan.status_code == 200
    assert today_plan.json()["items"] == []

    repeated = client.post(f"/api/v1/reviews/{review['id']}/carry-forward", json={})
    assert repeated.status_code == 200
    assert repeated.json()["created"] is False
    assert repeated.json()["task"]["id"] == task["id"]
    assert len(client.get("/api/v1/tasks").json()) == 1
    exported_review = client.get("/api/v1/export").json()["lifecycle_data"]["reviews"]
    carried_review = next(
        item for item in exported_review if item["id"] == review["id"]
    )
    assert carried_review["follow_up_task_id"] == task["id"]
    deleted = client.delete(f"/api/v1/reviews/{review['id']}/responses")
    assert deleted.status_code == 200
    assert len(client.get("/api/v1/tasks").json()) == 1


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
