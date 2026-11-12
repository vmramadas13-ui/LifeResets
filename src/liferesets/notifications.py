"""Local calendar import preview, private exports, and due-task reminders."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from liferesets.database import get_db
from liferesets.models import DailyPlan, Profile, Task
from liferesets.security import Authenticated, AuthenticatedWithCsrf

router = APIRouter(tags=["calendar and reminders"])


class CalendarImportPreviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_date: date
    ics_content: str = Field(min_length=1, max_length=1_000_000)
    day_start_time: time | None = None
    day_end_time: time | None = None

    @model_validator(mode="after")
    def valid_planning_hours(self) -> CalendarImportPreviewInput:
        if (self.day_start_time is None) != (self.day_end_time is None):
            raise ValueError("Provide both planning day hours or neither")
        if self.day_start_time is not None and self.day_end_time is not None:
            if (
                self.day_start_time.utcoffset() is not None
                or self.day_end_time.utcoffset() is not None
                or self.day_end_time <= self.day_start_time
            ):
                raise ValueError(
                    "Planning hours must be local times in ascending order"
                )
        return self


def _unfold_ics_lines(content: str) -> list[str]:
    unfolded: list[str] = []
    for line in (
        content.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ):
        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    return unfolded


def _ical_property(line: str) -> tuple[str, dict[str, str], str]:
    name_and_parameters, separator, value = line.partition(":")
    if not separator:
        return "", {}, ""
    parts = name_and_parameters.split(";")
    parameters: dict[str, str] = {}
    for part in parts[1:]:
        key, equals, parameter_value = part.partition("=")
        if equals:
            parameters[key.upper()] = parameter_value.strip('"')
    return parts[0].upper(), parameters, value.strip()


def _ical_temporal_value(
    value: str, parameters: dict[str, str], fallback_zone: ZoneInfo
) -> date | datetime:
    if parameters.get("VALUE", "").upper() == "DATE" or len(value) == 8:
        return datetime.strptime(value, "%Y%m%d").date()
    parsed = datetime.fromisoformat(
        value[:-1] + "+00:00" if value.endswith("Z") else value
    )
    if parsed.tzinfo is not None:
        return parsed
    timezone_name = parameters.get("TZID")
    timezone = ZoneInfo(timezone_name) if timezone_name else fallback_zone
    return parsed.replace(tzinfo=timezone)


def _merged_busy_windows(
    intervals: list[tuple[time, time]],
) -> list[tuple[time, time]]:
    merged: list[tuple[time, time]] = []
    for starts_at, ends_at in sorted(intervals):
        if merged and starts_at <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], ends_at))
        else:
            merged.append((starts_at, ends_at))
    return merged


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


@router.post("/api/v1/calendar/import-preview")
def preview_calendar_busy_times(
    request: CalendarImportPreviewInput,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Preview only the selected day's calendar busy times; save no event data."""
    lines = _unfold_ics_lines(request.ics_content)
    if "BEGIN:VCALENDAR" not in lines or "END:VCALENDAR" not in lines:
        raise HTTPException(status_code=422, detail="Choose a valid iCalendar file.")

    profile = db.get(Profile, auth.user.id)
    timezone_name = profile.timezone if profile else "UTC"
    try:
        user_zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        user_zone = ZoneInfo("UTC")
        timezone_name = "UTC"

    plan = db.scalar(
        select(DailyPlan).where(
            DailyPlan.user_id == auth.user.id,
            DailyPlan.plan_date == request.plan_date,
        )
    )
    day_start = request.day_start_time or (plan.day_start_time if plan else time(9))
    day_end = request.day_end_time or (plan.day_end_time if plan else time(21))
    day_start_at = datetime.combine(request.plan_date, day_start).replace(
        tzinfo=user_zone
    )
    day_end_at = datetime.combine(request.plan_date, day_end).replace(tzinfo=user_zone)

    intervals: list[tuple[time, time]] = []
    skipped = 0
    recurring_skipped = 0
    event_count = 0
    current: dict[str, tuple[dict[str, str], str]] | None = None
    for line in lines:
        name, parameters, value = _ical_property(line)
        if name == "BEGIN" and value.upper() == "VEVENT":
            if event_count >= 500:
                raise HTTPException(
                    status_code=422,
                    detail="The calendar file has too many events to preview at once.",
                )
            event_count += 1
            current = {}
        elif name == "END" and value.upper() == "VEVENT":
            if current is None:
                continue
            if "RRULE" in current:
                recurring_skipped += 1
                current = None
                continue
            if current.get("STATUS", ({}, ""))[1].upper() == "CANCELLED":
                current = None
                continue
            start_property = current.get("DTSTART")
            end_property = current.get("DTEND")
            if start_property is None:
                skipped += 1
                current = None
                continue
            try:
                starts_at = _ical_temporal_value(
                    start_property[1], start_property[0], user_zone
                )
                ends_at = (
                    _ical_temporal_value(end_property[1], end_property[0], user_zone)
                    if end_property
                    else None
                )
                if isinstance(starts_at, datetime):
                    if not isinstance(ends_at, datetime) or ends_at <= starts_at:
                        skipped += 1
                        current = None
                        continue
                    local_start = starts_at.astimezone(user_zone)
                    local_end = ends_at.astimezone(user_zone)
                else:
                    end_date = (
                        ends_at
                        if isinstance(ends_at, date)
                        else starts_at + timedelta(days=1)
                    )
                    if end_date <= starts_at:
                        skipped += 1
                        current = None
                        continue
                    if not starts_at <= request.plan_date < end_date:
                        current = None
                        continue
                    local_start = day_start_at
                    local_end = day_end_at

                clipped_start = max(local_start, day_start_at)
                clipped_end = min(local_end, day_end_at)
                if (
                    clipped_start.date() == request.plan_date
                    and clipped_end > clipped_start
                ):
                    intervals.append((clipped_start.time(), clipped_end.time()))
            except (ValueError, OverflowError, ZoneInfoNotFoundError):
                skipped += 1
            current = None
        elif current is not None and name in {"DTSTART", "DTEND", "RRULE", "STATUS"}:
            current[name] = (parameters, value)

    windows = _merged_busy_windows(intervals)
    return {
        "plan_date": request.plan_date.isoformat(),
        "timezone": timezone_name,
        "windows": [
            {
                "start_time": starts_at.isoformat(timespec="minutes"),
                "end_time": ends_at.isoformat(timespec="minutes"),
            }
            for starts_at, ends_at in windows
        ],
        "events_checked": event_count,
        "events_skipped": skipped,
        "recurring_events_skipped": recurring_skipped,
        "too_many_windows": len(windows) > 12,
        "can_apply": 0 < len(windows) <= 12,
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
