from uuid import UUID

from sqlalchemy.orm import Session

from liferesets.models import Task, User


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
    foreign_id = UUID("00000000-0000-0000-0000-000000000001")
    db_session.add(
        User(id=foreign_id, email="other@example.com", password_hash="unused")
    )
    db_session.add(Task(user_id=foreign_id, title="Foreign", status="completed"))
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
    assert "not a score of personal worth" in data["meaning"]
