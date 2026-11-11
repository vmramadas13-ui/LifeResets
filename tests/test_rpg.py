from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from liferesets.models import ProgressionEvent, Task, User


def _login(client, test_user: dict[str, object]) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": test_user["email"], "password": test_user["password"]},
    )
    assert response.status_code == 200
    client.headers.update({"X-CSRF-Token": client.cookies.get("lr-csrf")})


def test_rpg_status_requires_auth(client) -> None:
    assert client.get("/api/v1/rpg/status").status_code == 401


def test_rpg_progression_is_explainable_and_account_scoped(
    client, test_user, db_session: Session
) -> None:
    _login(client, test_user)
    db_session.add_all(
        [
            Task(user_id=test_user["id"], title="One", status="completed"),
            Task(user_id=test_user["id"], title="Two", status="completed"),
            Task(user_id=test_user["id"], title="Pending", status="pending"),
        ]
    )
    db_session.flush()
    completed_tasks = db_session.scalars(
        select(Task).where(Task.user_id == test_user["id"], Task.status == "completed")
    ).all()
    db_session.add_all(
        [
            ProgressionEvent(
                user_id=test_user["id"],
                task_id=task.id,
                event_type="task_completed",
                xp_delta=10,
                ruleset_version="starter-1",
                reason="Task marked complete.",
            )
            for task in completed_tasks
        ]
    )
    foreign_id = UUID("00000000-0000-0000-0000-000000000001")
    db_session.add(
        User(id=foreign_id, email="other@example.com", password_hash="unused")
    )
    foreign_task = Task(user_id=foreign_id, title="Foreign", status="completed")
    db_session.add(foreign_task)
    db_session.flush()
    db_session.add(
        ProgressionEvent(
            user_id=foreign_id,
            task_id=foreign_task.id,
            event_type="task_completed",
            xp_delta=1000,
            ruleset_version="starter-1",
            reason="Foreign task.",
        )
    )
    db_session.commit()

    response = client.get("/api/v1/rpg/status")
    assert response.status_code == 200
    data = response.json()
    assert data["total_xp"] == 20
    assert data["level"] == 1
    assert data["xp_in_level"] == 20
    assert data["xp_to_next_level"] == 80
    assert data["completed_tasks"] == 2
    assert data["achievements"] == ["first_completed_task"]
    assert data["rank"] == "E"
    assert data["ruleset"]["draft"] is True
    assert "not a score of personal worth" in data["meaning"]


def test_task_completion_uses_append_only_xp_and_reopens_with_correction(
    client, test_user
) -> None:
    _login(client, test_user)
    created = client.post("/api/v1/tasks", json={"title": "Practice SQL"})
    assert created.status_code == 201
    task_id = created.json()["id"]
    path = f"/api/v1/tasks/{task_id}"

    assert client.patch(path, json={"status": "completed"}).status_code == 200
    assert client.patch(path, json={"status": "completed"}).status_code == 200
    assert client.get("/api/v1/rpg/status").json()["total_xp"] == 10
    first_events = client.get("/api/v1/rpg/events").json()
    assert len(first_events) == 1
    assert first_events[0]["event_type"] == "task_completed"

    assert client.patch(path, json={"status": "pending"}).status_code == 200
    assert client.get("/api/v1/rpg/status").json()["total_xp"] == 0
    assert client.patch(path, json={"status": "completed"}).status_code == 200
    assert client.get("/api/v1/rpg/status").json()["total_xp"] == 10
    events = client.get("/api/v1/rpg/events").json()
    assert [item["xp_delta"] for item in reversed(events)] == [10, -10, 10]


def test_pause_suppresses_new_xp_without_changing_task_or_history(
    client, test_user
) -> None:
    _login(client, test_user)
    paused = client.patch(
        "/api/v1/rpg/character",
        json={"hunter_name": "My Hunter", "callsign": "VEE", "paused": True},
    )
    assert paused.status_code == 200
    assert paused.json()["callsign"] == "VEE"
    assert paused.json()["paused"] is True

    task = client.post("/api/v1/tasks", json={"title": "Read one page"}).json()
    assert (
        client.patch(
            f"/api/v1/tasks/{task['id']}", json={"status": "completed"}
        ).status_code
        == 200
    )
    assert client.get("/api/v1/rpg/status").json()["total_xp"] == 0
    assert client.get("/api/v1/tasks").json()[0]["status"] == "completed"

    resumed = client.patch("/api/v1/rpg/character", json={"paused": False})
    assert resumed.status_code == 200
    assert resumed.json()["hunter_name"] == "My Hunter"
    assert resumed.json()["paused"] is False


def test_progression_corrections_are_append_only_and_idempotent(
    client, test_user
) -> None:
    _login(client, test_user)
    task = client.post("/api/v1/tasks", json={"title": "Write a query"}).json()
    client.patch(f"/api/v1/tasks/{task['id']}", json={"status": "completed"})
    event = client.get("/api/v1/rpg/events").json()[0]

    response = client.post(
        f"/api/v1/rpg/events/{event['id']}/correct",
        json={"reason": "I marked the wrong action as complete."},
    )
    assert response.status_code == 201
    assert response.json()["xp_delta"] == -10
    assert response.json()["correction_of_id"] == event["id"]
    assert client.get("/api/v1/rpg/status").json()["total_xp"] == 0
    assert (
        client.post(
            f"/api/v1/rpg/events/{event['id']}/correct",
            json={"reason": "Duplicate correction request."},
        ).status_code
        == 409
    )


def test_skills_and_self_reported_evidence_are_owned_and_exported(
    client, test_user
) -> None:
    _login(client, test_user)
    skill = client.post(
        "/api/v1/rpg/skills",
        json={
            "domain": "learning",
            "name": "SQL",
            "definition": "Write and explain useful data queries.",
            "level": 2,
            "confidence": 55,
        },
    )
    assert skill.status_code == 201
    skill_id = skill.json()["id"]
    evidence = client.post(
        f"/api/v1/rpg/skills/{skill_id}/evidence",
        json={
            "summary": "Built a query for a small practice dataset.",
            "confidence": 65,
        },
    )
    assert evidence.status_code == 201
    assert evidence.json()["source"] == "self_report"
    assert evidence.json()["verified"] is False

    listed = client.get("/api/v1/rpg/skills").json()
    assert listed[0]["evidence"][0]["summary"].startswith("Built a query")
    assert (
        client.patch(
            f"/api/v1/rpg/skills/{skill_id}", json={"level": 3, "confidence": 60}
        ).json()["level"]
        == 3
    )
    assert (
        client.post(
            "/api/v1/rpg/skills",
            json={"name": "SQL", "definition": "Duplicate."},
        ).status_code
        == 409
    )

    export = client.get("/api/v1/export").json()["character_data"]
    assert export["character"]["hunter_name"] == "Hunter"
    assert export["skills"][0]["evidence"][0]["verified"] is False
    assert len(export["skills"]) == 1


def test_character_endpoints_are_authenticated_and_chronicle_is_scoped(
    client, test_user
) -> None:
    assert client.get("/api/v1/rpg/skills").status_code == 401
    _login(client, test_user)
    task = client.post("/api/v1/tasks", json={"title": "A private action"}).json()
    client.patch(f"/api/v1/tasks/{task['id']}", json={"status": "completed"})
    history = client.get("/api/v1/rpg/chronicle").json()
    assert any(item["title"] == "Task marked complete." for item in history)
    assert all("A private action" not in str(item) for item in history)
