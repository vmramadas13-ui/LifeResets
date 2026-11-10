from datetime import date
from uuid import UUID

from sqlalchemy.orm import Session

from liferesets.models import Task, User


def _login(client, test_user: dict[str, object]) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": test_user["email"], "password": test_user["password"]},
    )
    assert response.status_code == 200


def test_calendar_and_inbox_require_authentication(client) -> None:
    assert client.get("/api/v1/notifications/inbox").status_code == 401
    assert client.get("/api/v1/calendar.ics").status_code == 401


def test_in_app_inbox_and_calendar_export_are_private_and_read_only(
    client, test_user, db_session: Session
) -> None:
    _login(client, test_user)
    today = date(2026, 11, 11)
    db_session.add_all(
        [
            Task(
                user_id=test_user["id"],
                title="Review budget, then save;",
                due_date=date(2026, 11, 12),
            ),
            Task(user_id=test_user["id"], title="Old task", due_date=date(2026, 11, 1)),
            Task(
                user_id=test_user["id"],
                title="Completed task",
                due_date=date(2026, 11, 12),
                status="completed",
            ),
        ]
    )
    other = UUID("00000000-0000-0000-0000-000000000001")
    db_session.add(User(id=other, email="other@example.com", password_hash="unused"))
    db_session.add(Task(user_id=other, title="Private", due_date=date(2026, 11, 12)))
    db_session.commit()

    inbox = client.get(f"/api/v1/notifications/inbox?today={today}&days=7").json()
    assert inbox["delivery"] == "in_app_only"
    assert len(inbox["items"]) == 1
    assert inbox["items"][0]["title"] == "Review budget, then save;"

    calendar = client.get("/api/v1/calendar.ics")
    assert calendar.status_code == 200
    assert "text/calendar" in calendar.headers["content-type"]
    assert "Review budget\\, then save\\;" in calendar.text
    assert "Private" not in calendar.text
    assert calendar.text.count("BEGIN:VEVENT") == 3


def test_inbox_horizon_is_bounded(client, test_user) -> None:
    _login(client, test_user)
    assert client.get("/api/v1/notifications/inbox?days=32").status_code == 422
