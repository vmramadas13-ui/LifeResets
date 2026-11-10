from datetime import date
from uuid import UUID

from sqlalchemy.orm import Session

from liferesets.models import Goal, Task, User


def _login(client, test_user: dict[str, object]) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": test_user["email"], "password": test_user["password"]},
    )
    assert response.status_code == 200
    client.headers.update({"X-CSRF-Token": client.cookies.get("lr-csrf")})


def test_preview_requires_auth(client) -> None:
    assert client.get("/api/v1/plans/preview").status_code == 401


def test_preview_uses_owned_goals_and_tasks_without_writing(
    client, test_user, db_session: Session
) -> None:
    _login(client, test_user)
    user_id = test_user["id"]
    goal = Goal(user_id=user_id, domain="learning", title="Learn Python", priority=5)
    db_session.add(goal)
    db_session.flush()
    db_session.add(
        Task(
            user_id=user_id,
            goal_id=goal.id,
            title="Complete first lesson",
            due_date=date(2026, 11, 12),
        )
    )
    foreign_id = UUID("00000000-0000-0000-0000-000000000001")
    db_session.add(
        User(id=foreign_id, email="other@example.com", password_hash="unused")
    )
    db_session.add(Goal(user_id=foreign_id, domain="finance", title="Private goal"))
    db_session.commit()

    before = db_session.query(Goal).count(), db_session.query(Task).count()
    response = client.get("/api/v1/plans/preview?start_date=2026-11-11&days=7")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["start_date"] == "2026-11-11"
    assert data["end_date"] == "2026-11-17"
    assert [item["kind"] for item in data["quests"]] == ["existing_task"]
    assert data["quests"][0]["title"] == "Complete first lesson"
    assert "Private goal" not in response.text
    assert data["is_preview"] is True
    assert data["persisted"] is False
    assert data["generated_actions"] is False
    assert (db_session.query(Goal).count(), db_session.query(Task).count()) == before


def test_preview_bounds_days(client, test_user) -> None:
    _login(client, test_user)
    assert client.get("/api/v1/plans/preview?days=32").status_code == 422
