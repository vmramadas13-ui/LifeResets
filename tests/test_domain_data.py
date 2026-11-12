from datetime import date, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from liferesets.models import (
    DomainSubarea,
    Evidence,
    Goal,
    GoalMetric,
    Habit,
    HabitCheckIn,
    Task,
    User,
)


def _login(client, test_user: dict[str, object]) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": test_user["email"], "password": test_user["password"]},
    )
    assert response.status_code == 200
    client.headers.update({"X-CSRF-Token": client.cookies.get("lr-csrf")})


def test_domains_are_private_and_user_configurable(client, test_user) -> None:
    assert client.get("/api/v1/domains").status_code == 401
    _login(client, test_user)
    domains = client.get("/api/v1/domains").json()
    assert len(domains) == 8
    assert "empire" not in {domain["code"] for domain in domains}
    assert all(domain["enabled"] for domain in domains)
    existing_goal = client.post(
        "/api/v1/goals", json={"domain": "career", "title": "Existing goal"}
    )
    assert existing_goal.status_code == 201

    settings = []
    career_order = next(
        domain["sort_order"] for domain in domains if domain["code"] == "career"
    )
    finance_order = next(
        domain["sort_order"] for domain in domains if domain["code"] == "finance"
    )
    for domain in domains:
        item = {key: domain[key] for key in ("code", "name", "sort_order", "enabled")}
        if item["code"] == "career":
            item.update(name="Work", sort_order=1, enabled=False)
            item["sort_order"] = finance_order
        elif item["code"] == "finance":
            item["sort_order"] = career_order
        settings.append(item)
    saved = client.put("/api/v1/domains/settings", json={"domains": settings})
    assert saved.status_code == 200, saved.text
    configured = saved.json()
    assert configured[0]["code"] == "finance"
    assert next(item for item in configured if item["code"] == "career") == {
        **next(item for item in domains if item["code"] == "career"),
        "name": "Work",
        "sort_order": finance_order,
        "enabled": False,
    }
    hidden_goal = client.post(
        "/api/v1/goals", json={"domain": "career", "title": "New goal"}
    )
    assert hidden_goal.status_code == 422
    assert any(
        item["id"] == existing_goal.json()["id"]
        for item in client.get("/api/v1/goals").json()
    )
    all_hidden = [
        {
            "code": item["code"],
            "name": item["name"],
            "sort_order": item["sort_order"],
            "enabled": False,
        }
        for item in configured
    ]
    assert (
        client.put("/api/v1/domains/settings", json={"domains": all_hidden}).status_code
        == 422
    )
    exported = client.get("/api/v1/export").json()["profile"]["preferences"]
    assert exported["life_domains"]["career"]["name"] == "Work"


def test_custom_subareas_can_be_used_on_goals_and_deleted_safely(
    client, test_user, db_session: Session
) -> None:
    _login(client, test_user)
    created = client.post(
        "/api/v1/domains/career/subareas", json={"name": "  Product design  "}
    )
    assert created.status_code == 201, created.text
    subarea = created.json()
    assert subarea["name"] == "Product design"

    domains = client.get("/api/v1/domains").json()
    career = next(item for item in domains if item["code"] == "career")
    assert career["subareas"] == [{"id": subarea["id"], "name": "Product design"}]
    saved_settings = client.put(
        "/api/v1/domains/settings",
        json={
            "domains": [
                {key: domain[key] for key in ("code", "name", "sort_order", "enabled")}
                for domain in domains
            ]
        },
    )
    assert saved_settings.status_code == 200
    assert (
        next(item for item in saved_settings.json() if item["code"] == "career")[
            "subareas"
        ]
        == career["subareas"]
    )
    duplicate = client.post(
        "/api/v1/domains/career/subareas", json={"name": "product DESIGN"}
    )
    assert duplicate.status_code == 409

    foreign_user = User(email="other@example.com", password_hash="unused")
    db_session.add(foreign_user)
    db_session.flush()
    foreign_subarea = DomainSubarea(
        user_id=foreign_user.id, domain="career", name="Private area"
    )
    db_session.add(foreign_subarea)
    db_session.commit()
    visible_domains = client.get("/api/v1/domains").json()
    assert all(
        foreign_subarea.name != entry["name"]
        for area in visible_domains
        for entry in area["subareas"]
    )
    foreign_assignment = client.post(
        "/api/v1/goals",
        json={
            "domain": "career",
            "subarea_id": str(foreign_subarea.id),
            "title": "Must not attach",
        },
    )
    assert foreign_assignment.status_code == 404
    assert (
        client.patch(
            f"/api/v1/domains/subareas/{foreign_subarea.id}",
            json={"name": "Changed"},
        ).status_code
        == 404
    )

    renamed = client.patch(
        f"/api/v1/domains/subareas/{subarea['id']}",
        json={"name": "Product strategy"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Product strategy"
    goal = client.post(
        "/api/v1/goals",
        json={
            "domain": "career",
            "subarea_id": subarea["id"],
            "title": "Build a portfolio",
        },
    )
    assert goal.status_code == 201, goal.text
    assert goal.json()["subarea_name"] == "Product strategy"
    finance_goal = client.post(
        "/api/v1/goals", json={"domain": "finance", "title": "Review budget"}
    )
    assert finance_goal.status_code == 201
    mismatch = client.patch(
        f"/api/v1/goals/{finance_goal.json()['id']}",
        json={"subarea_id": subarea["id"]},
    )
    assert mismatch.status_code == 422

    exported = client.get("/api/v1/export").json()["domain_data"]
    assert exported["subareas"] == [
        {"id": subarea["id"], "domain": "career", "name": "Product strategy"}
    ]
    assert exported["goals"][0]["subarea_name"] == "Product strategy"

    deleted = client.delete(f"/api/v1/domains/subareas/{subarea['id']}")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True, "unassigned_goals": 1}
    goals = client.get("/api/v1/goals").json()
    preserved = next(item for item in goals if item["id"] == goal.json()["id"])
    assert preserved["domain"] == "career"
    assert preserved["subarea_id"] is None
    assert (
        client.delete(f"/api/v1/domains/subareas/{foreign_subarea.id}").status_code
        == 404
    )


def test_goal_task_habit_and_evidence_flow(client, test_user) -> None:
    _login(client, test_user)
    today = date.today()
    updated_on = today.isoformat()
    appended_on = (today + timedelta(days=1)).isoformat()
    backfilled_on = (today - timedelta(days=2)).isoformat()
    goal_response = client.post(
        "/api/v1/goals",
        json={
            "domain": "learning",
            "title": "Build a steady study practice",
            "target_date": "2027-06-30",
            "metrics": [
                {
                    "name": "Practice sessions",
                    "unit": "sessions",
                    "baseline_value": "0",
                    "target_value": "10",
                    "current_value": "1",
                    "confidence": 70,
                }
            ],
        },
    )
    assert goal_response.status_code == 201, goal_response.text
    goal = goal_response.json()
    metric = goal["metrics"][0]
    assert metric["unit"] == "sessions"
    assert metric["baseline_value"] == "0.0000"
    assert metric["confidence"] == 70
    assert metric["history"][0]["value"] == "1.0000"
    assert metric["history"][0]["confidence"] == 70

    updated_metric = client.patch(
        f"/api/v1/metrics/{metric['id']}",
        json={"current_value": "2", "measured_on": updated_on, "confidence": 80},
    )
    assert updated_metric.status_code == 200, updated_metric.text
    assert updated_metric.json()["history"][0]["value"] == "2.0000"
    assert updated_metric.json()["history"][0]["measured_on"] == updated_on
    history_response = client.get(f"/api/v1/metrics/{metric['id']}/history")
    assert history_response.status_code == 200
    assert history_response.json()[0]["value"] == "2.0000"
    assert history_response.json()[0]["measured_on"] == updated_on
    assert history_response.json()[0]["confidence"] == 80

    appended = client.post(
        f"/api/v1/metrics/{metric['id']}/measurements",
        json={"value": "3", "measured_on": appended_on, "confidence": 90},
    )
    assert appended.status_code == 201, appended.text
    refreshed = client.get(f"/api/v1/goals/{goal['id']}").json()["metrics"][0]
    assert refreshed["current_value"] == "3.0000"
    assert len(refreshed["history"]) == 3
    assert refreshed["history"][0]["measured_on"] == appended_on
    backfilled = client.post(
        f"/api/v1/metrics/{metric['id']}/measurements",
        json={"value": "0", "measured_on": backfilled_on, "confidence": 25},
    )
    assert backfilled.status_code == 201
    refreshed = client.get(f"/api/v1/goals/{goal['id']}").json()["metrics"][0]
    assert refreshed["current_value"] == "3.0000"
    assert refreshed["history"][0]["measured_on"] == appended_on
    assert refreshed["history"][-1]["measured_on"] == backfilled_on
    export_metric = client.get("/api/v1/export").json()["domain_data"]["goals"][0][
        "metrics"
    ][0]
    assert len(export_metric["history"]) == 4
    insight_metric = client.get("/api/v1/insights/progress").json()["goals"][0][
        "metrics"
    ][0]
    assert insight_metric["history_count"] == 4
    assert insight_metric["confidence"] == 90

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


def test_habit_check_ins_are_reversible_and_exported(client, test_user) -> None:
    assert client.get("/api/v1/habits").status_code == 401
    _login(client, test_user)
    habit_response = client.post(
        "/api/v1/habits",
        json={
            "cue": "after breakfast",
            "action": "review one lesson",
            "frequency": "daily",
            "minimum_version": "review one note",
            "recovery_action": "restart with one note",
        },
    )
    assert habit_response.status_code == 201, habit_response.text
    habit = habit_response.json()
    assert habit["check_ins"] == []
    day = date.today().isoformat()

    completed = client.post(
        f"/api/v1/habits/{habit['id']}/check-ins",
        json={"status": "completed", "recorded_on": day},
    )
    assert completed.status_code == 201, completed.text
    skipped = client.post(
        f"/api/v1/habits/{habit['id']}/check-ins",
        json={
            "status": "skipped",
            "recorded_on": day,
            "reason": "Plans changed",
        },
    )
    assert skipped.status_code == 201, skipped.text

    history = client.get(f"/api/v1/habits/{habit['id']}/check-ins")
    assert history.status_code == 200
    assert [item["status"] for item in history.json()] == ["skipped", "completed"]
    assert history.json()[0]["reason"] == "Plans changed"
    listed = client.get("/api/v1/habits").json()[0]
    assert len(listed["check_ins"]) == 2

    paused = client.patch(f"/api/v1/habits/{habit['id']}", json={"is_active": False})
    assert paused.status_code == 200
    assert paused.json()["is_active"] is False
    assert len(paused.json()["check_ins"]) == 2
    resumed = client.patch(f"/api/v1/habits/{habit['id']}", json={"is_active": True})
    assert resumed.status_code == 200
    exported = client.get("/api/v1/export").json()["domain_data"]["habits"][0]
    assert len(exported["check_ins"]) == 2


def test_weekly_habit_schedule_respects_weekdays_dates_and_pause(
    client, test_user
) -> None:
    _login(client, test_user)
    today = date.today()
    habit_response = client.post(
        "/api/v1/habits",
        json={
            "cue": "after breakfast",
            "action": "take a short walk",
            "frequency": "weekly",
            "weekdays": [today.isoweekday()],
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=7)).isoformat(),
            "reminder_preference": "in_app",
            "minimum_version": "walk for five minutes",
            "recovery_action": "restart with a short walk",
        },
    )
    assert habit_response.status_code == 201, habit_response.text
    habit = habit_response.json()
    assert habit["weekdays"] == [today.isoweekday()]
    assert habit["start_date"] == today.isoformat()
    assert habit["end_date"] == (today + timedelta(days=7)).isoformat()
    assert habit["reminder_preference"] == "in_app"
    assert habit["due_today"] is True

    unscheduled_day = client.post(
        f"/api/v1/habits/{habit['id']}/check-ins",
        json={
            "status": "completed",
            "recorded_on": (today + timedelta(days=1)).isoformat(),
        },
    )
    assert unscheduled_day.status_code == 422

    logged = client.post(
        f"/api/v1/habits/{habit['id']}/check-ins",
        json={"status": "completed", "recorded_on": today.isoformat()},
    )
    assert logged.status_code == 201, logged.text

    paused = client.patch(f"/api/v1/habits/{habit['id']}", json={"is_active": False})
    assert paused.status_code == 200
    assert paused.json()["due_today"] is False
    assert paused.json()["next_due_on"] is None
    while_paused = client.post(
        f"/api/v1/habits/{habit['id']}/check-ins",
        json={
            "status": "skipped",
            "recorded_on": (today + timedelta(days=7)).isoformat(),
        },
    )
    assert while_paused.status_code == 422


def test_custom_interval_keeps_its_dates_after_a_skipped_occurrence(
    client, test_user
) -> None:
    _login(client, test_user)
    today = date.today()
    start_date = today - timedelta(days=4)
    end_date = today + timedelta(days=10)
    habit_response = client.post(
        "/api/v1/habits",
        json={
            "cue": "after lunch",
            "action": "review one lesson",
            "frequency": "custom",
            "interval_days": 3,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "minimum_version": "review one note",
            "recovery_action": "restart with one note",
        },
    )
    assert habit_response.status_code == 201, habit_response.text
    habit = habit_response.json()
    elapsed = (today - start_date).days
    expected_next = today + timedelta(days=(-elapsed) % 3)
    assert habit["interval_days"] == 3
    assert habit["next_due_on"] == expected_next.isoformat()

    skipped = client.post(
        f"/api/v1/habits/{habit['id']}/check-ins",
        json={"status": "skipped", "recorded_on": start_date.isoformat()},
    )
    assert skipped.status_code == 201, skipped.text
    after_skip = client.get("/api/v1/habits").json()[0]
    assert after_skip["next_due_on"] == expected_next.isoformat()
    assert after_skip["check_ins"][0]["status"] == "skipped"

    outside_window = client.post(
        f"/api/v1/habits/{habit['id']}/check-ins",
        json={
            "status": "completed",
            "recorded_on": (end_date + timedelta(days=1)).isoformat(),
        },
    )
    assert outside_window.status_code == 422


def test_weekly_any_day_habit_has_one_check_in_per_week(client, test_user) -> None:
    _login(client, test_user)
    today = date.today()
    current_week_start = today - timedelta(days=today.isoweekday() - 1)
    previous_week_start = current_week_start - timedelta(days=7)
    habit_response = client.post(
        "/api/v1/habits",
        json={
            "cue": "at a quiet moment",
            "action": "write a short reflection",
            "frequency": "weekly",
            "start_date": (previous_week_start - timedelta(days=7)).isoformat(),
            "minimum_version": "write one sentence",
            "recovery_action": "return next week",
        },
    )
    assert habit_response.status_code == 201, habit_response.text
    habit = habit_response.json()
    assert habit["weekdays"] == []

    first_entry = client.post(
        f"/api/v1/habits/{habit['id']}/check-ins",
        json={
            "status": "skipped",
            "recorded_on": previous_week_start.isoformat(),
        },
    )
    assert first_entry.status_code == 201, first_entry.text
    second_entry = client.post(
        f"/api/v1/habits/{habit['id']}/check-ins",
        json={
            "status": "completed",
            "recorded_on": (previous_week_start + timedelta(days=4)).isoformat(),
        },
    )
    assert second_entry.status_code == 422

    current = client.get("/api/v1/habits").json()[0]
    assert current["due_today"] is True
    assert current["next_due_on"] == today.isoformat()


def test_account_ownership_and_client_cannot_claim_verified_evidence(
    client, test_user, db_session: Session
) -> None:
    _login(client, test_user)
    foreign_user = User(email="other@example.com", password_hash="unused")
    db_session.add(foreign_user)
    db_session.flush()
    foreign_goal = Goal(user_id=foreign_user.id, domain="career", title="Private")
    foreign_metric = GoalMetric(
        goal=foreign_goal,
        name="Private measure",
        unit="sessions",
        target_value=10,
        current_value=2,
    )
    foreign_habit = Habit(
        user_id=foreign_user.id,
        cue="morning",
        action="private routine",
        frequency="daily",
        minimum_version="one step",
        recovery_action="try another day",
    )
    foreign_check_in = HabitCheckIn(
        habit=foreign_habit,
        recorded_on=date.today(),
        status="completed",
    )
    db_session.add(foreign_goal)
    db_session.add(foreign_metric)
    db_session.add_all([foreign_habit, foreign_check_in])
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
    assert client.get(f"/api/v1/metrics/{foreign_metric.id}/history").status_code == 404
    assert (
        client.post(
            f"/api/v1/metrics/{foreign_metric.id}/measurements",
            json={"value": 3, "measured_on": "2026-11-12"},
        ).status_code
        == 404
    )
    assert client.get(f"/api/v1/habits/{foreign_habit.id}/check-ins").status_code == 404
    assert (
        client.post(
            f"/api/v1/habits/{foreign_habit.id}/check-ins",
            json={"status": "completed"},
        ).status_code
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
    habit = client.post(
        "/api/v1/habits",
        json={
            "goal_id": goal["id"],
            "cue": "morning",
            "action": "study",
            "frequency": "daily",
            "minimum_version": "5 min",
            "recovery_action": "restart tomorrow",
        },
    ).json()
    client.post(
        f"/api/v1/habits/{habit['id']}/check-ins",
        json={"status": "completed", "recorded_on": date.today().isoformat()},
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
    assert (
        db_session.scalar(
            select(HabitCheckIn).where(HabitCheckIn.habit_id == UUID(habit["id"]))
        )
        is None
    )
