from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from liferesets.models import Evidence, Goal, Habit, Task, User


def _login(client, test_user: dict[str, object]) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": test_user["email"], "password": test_user["password"]},
    )
    assert response.status_code == 200
    client.headers.update({"X-CSRF-Token": client.cookies.get("lr-csrf")})


def test_domains_are_private_fixed_catalog(client, test_user) -> None:
    assert client.get("/api/v1/domains").status_code == 401
    _login(client, test_user)
    domains = client.get("/api/v1/domains").json()
    assert len(domains) == 8
    assert "empire" not in {domain["code"] for domain in domains}


def test_goal_task_habit_and_evidence_flow(client, test_user) -> None:
    _login(client, test_user)
    goal_response = client.post(
        "/api/v1/goals",
        json={
            "domain": "finance",
            "title": "Build an emergency fund",
            "target_date": "2027-06-30",
            "metrics": [
                {
                    "name": "Emergency savings",
                    "unit": "INR",
                    "baseline_value": "-1000",
                    "target_value": "100000",
                    "current_value": "0",
                }
            ],
        },
    )
    assert goal_response.status_code == 201, goal_response.text
    goal = goal_response.json()
    assert goal["metrics"][0]["unit"] == "INR"
    assert goal["metrics"][0]["baseline_value"] == "-1000.0000"

    task_response = client.post(
        "/api/v1/tasks",
        json={
            "goal_id": goal["id"],
            "title": "Review monthly budget",
            "due_date": "2026-12-01",
        },
    )
    assert task_response.status_code == 201, task_response.text
    task = task_response.json()
    assert task["due_date"] == "2026-12-01"
    completed = client.patch(
        f"/api/v1/tasks/{task['id']}", json={"status": "completed"}
    )
    assert completed.status_code == 200
    assert completed.json()["completed_at"].endswith("+00:00")

    invalid_habit = client.post(
        "/api/v1/habits",
        json={
            "goal_id": goal["id"],
            "cue": "after lunch",
            "action": "save",
            "frequency": "custom",
            "minimum_version": "save 100",
            "recovery_action": "resume tomorrow",
        },
    )
    assert invalid_habit.status_code == 422
    habit_response = client.post(
        "/api/v1/habits",
        json={
            "goal_id": goal["id"],
            "cue": "after payday",
            "action": "transfer savings",
            "frequency": "custom",
            "custom_schedule": "on payday",
            "minimum_version": "transfer any amount",
            "recovery_action": "try next payday",
        },
    )
    assert habit_response.status_code == 201, habit_response.text

    evidence_response = client.post(
        "/api/v1/evidence",
        json={
            "goal_id": goal["id"],
            "task_id": task["id"],
            "summary": "Budget reviewed",
        },
    )
    assert evidence_response.status_code == 201, evidence_response.text
    evidence = evidence_response.json()
    assert evidence["source"] == "self_report"
    assert evidence["is_verified"] is False
    assert (
        client.get("/api/v1/export").json()["domain_data"]["evidence"][0]["id"]
        == evidence["id"]
    )


def test_account_ownership_and_client_cannot_claim_verified_evidence(
    client, test_user, db_session: Session
) -> None:
    _login(client, test_user)
    foreign_user = User(email="other@example.com", password_hash="unused")
    db_session.add(foreign_user)
    db_session.flush()
    foreign_goal = Goal(user_id=foreign_user.id, domain="career", title="Private")
    db_session.add(foreign_goal)
    db_session.commit()

    assert client.get(f"/api/v1/goals/{foreign_goal.id}").status_code == 404
    assert (
        client.patch(
            f"/api/v1/goals/{foreign_goal.id}", json={"title": "Claim"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/tasks", json={"goal_id": str(foreign_goal.id), "title": "Claim"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/evidence",
            json={
                "goal_id": str(foreign_goal.id),
                "summary": "Claim",
                "source": "verified",
                "is_verified": True,
            },
        ).status_code
        == 422
    )
    assert (
        client.patch(f"/api/v1/metrics/{uuid4()}", json={"target_value": 1}).status_code
        == 404
    )


def test_list_endpoints_are_scoped_and_account_delete_cascades(
    client, test_user, db_session: Session
) -> None:
    _login(client, test_user)
    goal = client.post(
        "/api/v1/goals", json={"domain": "learning", "title": "Learn"}
    ).json()
    task = client.post(
        "/api/v1/tasks", json={"goal_id": goal["id"], "title": "Practice"}
    ).json()
    client.post(
        "/api/v1/habits",
        json={
            "goal_id": goal["id"],
            "cue": "morning",
            "action": "study",
            "frequency": "daily",
            "minimum_version": "5 min",
            "recovery_action": "restart tomorrow",
        },
    )
    client.post(
        "/api/v1/evidence", json={"task_id": task["id"], "summary": "Session completed"}
    )
    assert len(client.get("/api/v1/goals").json()) == 1
    assert len(client.get("/api/v1/tasks").json()) == 1
    assert len(client.get("/api/v1/habits").json()) == 1
    assert len(client.get("/api/v1/evidence").json()) == 1

    response = client.request(
        "DELETE",
        "/api/v1/account",
        json={
            "current_password": test_user["password"],
            "confirmation": "DELETE MY ACCOUNT",
        },
    )
    assert response.status_code == 204
    assert db_session.scalar(select(Goal).where(Goal.id == UUID(goal["id"]))) is None
    assert db_session.scalar(select(Task).where(Task.id == UUID(task["id"]))) is None
    assert (
        db_session.scalar(select(Habit).where(Habit.user_id == test_user["id"])) is None
    )
    assert (
        db_session.scalar(select(Evidence).where(Evidence.user_id == test_user["id"]))
        is None
    )
