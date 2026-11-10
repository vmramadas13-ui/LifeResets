"""Local due-task inbox and private iCalendar export; no outbound delivery."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from liferesets.database import get_db
from liferesets.models import Task
from liferesets.security import Authenticated

router = APIRouter(tags=["calendar and reminders"])


def _ics_escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
        .replace("\r", "")
    )


@router.get("/api/v1/notifications/inbox")
def notification_inbox(
    auth: Authenticated,
    db: Session = Depends(get_db),
    days: int = Query(default=7, ge=0, le=31),
    today: date = Query(default_factory=date.today),
) -> dict[str, object]:
    """Show local pending tasks due between today and the requested horizon."""
    end = today + timedelta(days=days)
    tasks = db.scalars(
        select(Task)
        .where(
            Task.user_id == auth.user.id,
            Task.status == "pending",
            Task.due_date.is_not(None),
            Task.due_date >= today,
            Task.due_date <= end,
        )
        .order_by(Task.due_date, Task.created_at)
    ).all()
    return {
        "items": [
            {
                "task_id": str(task.id),
                "title": task.title,
                "due_date": task.due_date.isoformat(),
            }
            for task in tasks
        ],
        "delivery": "in_app_only",
    }


@router.get("/api/v1/calendar.ics")
def export_calendar(auth: Authenticated, db: Session = Depends(get_db)) -> Response:
    """Export due-dated tasks as a private, read-only iCalendar file."""
    tasks = db.scalars(
        select(Task)
        .where(Task.user_id == auth.user.id, Task.due_date.is_not(None))
        .order_by(Task.due_date, Task.id)
    ).all()
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//LifeResets//Calendar//EN",
        "CALSCALE:GREGORIAN",
    ]
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    for task in tasks:
        due = task.due_date.strftime("%Y%m%d")
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{task.id}@liferesets.local",
                f"DTSTAMP:{stamp}",
                f"DTSTART;VALUE=DATE:{due}",
                f"SUMMARY:{_ics_escape(task.title)}",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return Response(
        content="\r\n".join(lines) + "\r\n",
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="liferesets.ics"'},
    )
