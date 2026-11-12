from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from liferesets.models import DailyPlan, Task, User


def _login(client, test_user: dict[str, object]) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": test_user["email"], "password": test_user["password"]},
    )
    assert response.status_code == 200
    client.headers.update({"X-CSRF-Token": client.cookies.get("lr-csrf")})


def test_calendar_and_inbox_require_authentication(client) -> None:
    assert client.get("/api/v1/notifications/inbox").status_code == 401
    assert client.get("/api/v1/calendar.ics").status_code == 401
    assert client.post("/api/v1/calendar/import-preview", json={}).status_code == 401


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


def test_calendar_import_preview_merges_private_busy_times_without_saving_events(
    client, test_user, db_session: Session
) -> None:
    _login(client, test_user)
    ics_content = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
DTSTART;TZID=Asia/Kolkata:20261113T100000
DTEND;TZID=Asia/Kolkata:20261113T110000
SUMMARY:Private appointment
END:VEVENT
BEGIN:VEVENT
DTSTART;TZID=Asia/Kolkata:20261113T103000
DTEND;TZID=Asia/Kolkata:20261113T120000
SUMMARY:Another private appointment
END:VEVENT
BEGIN:VEVENT
DTSTART:20261113T043000Z
DTEND:20261113T050000Z
RRULE:FREQ=DAILY
SUMMARY:Recurring event
END:VEVENT
END:VCALENDAR
"""
    response = client.post(
        "/api/v1/calendar/import-preview",
        json={"plan_date": "2026-11-13", "ics_content": ics_content},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["timezone"] == "Asia/Kolkata"
    assert result["windows"] == [{"start_time": "10:00", "end_time": "12:00"}]
    assert result["recurring_events_skipped"] == 1
    assert result["can_apply"] is True
    assert "Private appointment" not in response.text
    assert "RRULE" not in response.text
    assert db_session.scalar(select(DailyPlan)) is None


def test_calendar_import_preview_handles_all_day_and_rejects_invalid_files(
    client, test_user
) -> None:
    _login(client, test_user)
    all_day = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
DTSTART;VALUE=DATE:20261113
DTEND;VALUE=DATE:20261114
SUMMARY:Private all day event
END:VEVENT
END:VCALENDAR
"""
    response = client.post(
        "/api/v1/calendar/import-preview",
        json={"plan_date": "2026-11-13", "ics_content": all_day},
    )
    assert response.status_code == 200, response.text
    assert response.json()["windows"] == [{"start_time": "09:00", "end_time": "21:00"}]
    invalid = client.post(
        "/api/v1/calendar/import-preview",
        json={"plan_date": "2026-11-13", "ics_content": "not a calendar"},
    )
    assert invalid.status_code == 422
