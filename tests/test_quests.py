from sqlalchemy.orm import Session

from liferesets.models import Goal, Quest, QuestStep, Task, User


def _login(client, test_user: dict[str, object]) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": test_user["email"], "password": test_user["password"]},
    )
    assert response.status_code == 200
    client.headers.update({"X-CSRF-Token": client.cookies.get("lr-csrf")})


def test_quests_require_authentication(client) -> None:
    assert client.get("/api/v1/quests").status_code == 401
    assert (
        client.post(
            "/api/v1/quests",
            json={
                "title": "A private quest",
                "steps": [{"title": "First"}, {"title": "Second"}],
            },
        ).status_code
        == 401
    )


def test_quest_steps_are_plannable_and_drive_progress_and_lifecycle(
    client, test_user
) -> None:
    _login(client, test_user)
    goal = client.post(
        "/api/v1/goals",
        json={"domain": "learning", "title": "Build a portfolio"},
    )
    assert goal.status_code == 201, goal.text

    created = client.post(
        "/api/v1/quests",
        json={
            "title": "  Prepare a portfolio review  ",
            "description": "  Build confidence through small steps.  ",
            "goal_id": goal.json()["id"],
            "steps": [
                {"title": "Choose one project"},
                {"title": "Write the case study"},
                {"title": "Ask a peer for feedback"},
            ],
        },
    )
    assert created.status_code == 201, created.text
    quest = created.json()
    assert quest["title"] == "Prepare a portfolio review"
    assert quest["description"] == "Build confidence through small steps."
    assert quest["goal_id"] == goal.json()["id"]
    assert quest["status"] == "active"
    assert quest["progress_percent"] == 0
    assert [step["position"] for step in quest["steps"]] == [0, 1, 2]
    assert all(step["status"] == "pending" for step in quest["steps"])

    step = quest["steps"][0]
    complete = client.patch(
        f"/api/v1/tasks/{step['task_id']}", json={"status": "completed"}
    )
    assert complete.status_code == 200, complete.text
    progress = client.get(f"/api/v1/quests/{quest['id']}").json()
    assert progress["status"] == "active"
    assert progress["completed_steps"] == 1
    assert progress["progress_percent"] == 33

    for remaining_step in quest["steps"][1:]:
        response = client.patch(
            f"/api/v1/tasks/{remaining_step['task_id']}",
            json={"status": "completed"},
        )
        assert response.status_code == 200, response.text
    completed = client.get(f"/api/v1/quests/{quest['id']}").json()
    assert completed["status"] == "completed"
    assert completed["progress_percent"] == 100

    edited = client.patch(
        f"/api/v1/quests/{quest['id']}",
        json={"title": "A polished portfolio review", "description": "  "},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["title"] == "A polished portfolio review"
    assert edited.json()["description"] is None

    archived = client.patch(
        f"/api/v1/quests/{quest['id']}", json={"status": "archived"}
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    restored = client.patch(f"/api/v1/quests/{quest['id']}", json={"status": "active"})
    assert restored.status_code == 200
    assert restored.json()["status"] == "completed"

    exported = client.get("/api/v1/export").json()["quests"]
    assert len(exported) == 1
    assert exported[0]["id"] == quest["id"]
    assert exported[0]["completed_steps"] == 3


def test_quests_require_multiple_steps_and_respect_account_ownership(
    client, test_user, db_session: Session
) -> None:
    _login(client, test_user)
    foreign_user = User(email="other-quest@example.com", password_hash="unused")
    db_session.add(foreign_user)
    db_session.flush()
    foreign_goal = Goal(user_id=foreign_user.id, domain="career", title="Private goal")
    foreign_quest = Quest(user_id=foreign_user.id, title="Private quest")
    foreign_quest.steps.append(
        QuestStep(task=Task(user=foreign_user, title="Private step"), position=0)
    )
    db_session.add_all([foreign_goal, foreign_quest])
    db_session.commit()

    too_short = client.post(
        "/api/v1/quests",
        json={"title": "Too short", "steps": [{"title": "One step"}]},
    )
    assert too_short.status_code == 422
    foreign_goal_attempt = client.post(
        "/api/v1/quests",
        json={
            "title": "Cannot link a private goal",
            "goal_id": str(foreign_goal.id),
            "steps": [{"title": "First"}, {"title": "Second"}],
        },
    )
    assert foreign_goal_attempt.status_code == 404
    assert client.get(f"/api/v1/quests/{foreign_quest.id}").status_code == 404
    assert (
        client.patch(
            f"/api/v1/quests/{foreign_quest.id}", json={"status": "archived"}
        ).status_code
        == 404
    )
