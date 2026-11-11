from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from liferesets.models import DailyPlan, DailyPlanItem, Task, User


def _login(client, test_user: dict[str, object]) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": test_user["email"], "password": test_user["password"]},
    )
    assert response.status_code == 200
    client.headers.update({"X-CSRF-Token": client.cookies.get("lr-csrf")})


def _create_task(client, title: str, due_date: str | None = None) -> dict[str, object]:
    payload: dict[str, object] = {"title": title}
    if due_date is not None:
        payload["due_date"] = due_date
    response = client.post("/api/v1/tasks", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_daily_plan_requires_authentication(client) -> None:
    assert client.get("/api/v1/daily-plans/2026-11-11").status_code == 401
    assert (
        client.put(
            "/api/v1/daily-plans/2026-11-11",
            json={"capacity_minutes": 60, "energy": "medium", "items": []},
        ).status_code
        == 401
    )


def test_plan_saves_capacity_energy_and_user_task_decisions(
    client, test_user, db_session: Session
) -> None:
    _login(client, test_user)
    task_a = _create_task(client, "Study a Python lesson", "2026-11-11")
    task_b = _create_task(client, "Take a short walk", "2026-11-11")
    task_c = _create_task(client, "Review notes", "2026-11-11")

    unsaved = client.get("/api/v1/daily-plans/2026-11-11")
    assert unsaved.status_code == 200
    assert unsaved.json()["is_saved"] is False
    assert unsaved.json()["items"] == []

    saved = client.put(
        "/api/v1/daily-plans/2026-11-11",
        json={
            "capacity_minutes": 90,
            "energy": "low",
            "items": [
                {"task_id": task_a["id"], "planned_minutes": 30},
                {"task_id": task_b["id"], "planned_minutes": 15},
                {"task_id": task_c["id"], "planned_minutes": 20},
            ],
        },
    )
    assert saved.status_code == 200, saved.text
    plan = saved.json()
    assert plan["is_saved"] is True
    assert plan["capacity_minutes"] == 90
    assert plan["energy"] == "low"
    assert plan["planned_minutes"] == 65
    assert [item["title"] for item in plan["items"]] == [
        "Study a Python lesson",
        "Take a short walk",
        "Review notes",
    ]

    item_a, item_b, item_c = plan["items"]
    completed = client.patch(
        f"/api/v1/daily-plans/2026-11-11/items/{item_a['id']}",
        json={"status": "completed"},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completed"
    assert completed.json()["task_status"] == "completed"

    deferred = client.patch(
        f"/api/v1/daily-plans/2026-11-11/items/{item_b['id']}",
        json={"status": "deferred", "defer_to": "2026-11-13"},
    )
    assert deferred.status_code == 200, deferred.text
    assert deferred.json()["deferred_to"] == "2026-11-13"
    assert deferred.json()["due_date_at_planning"] == "2026-11-11"
    assert deferred.json()["due_date"] == "2026-11-13"

    dropped = client.patch(
        f"/api/v1/daily-plans/2026-11-11/items/{item_c['id']}",
        json={"status": "dropped"},
    )
    assert dropped.status_code == 200, dropped.text
    assert dropped.json()["status"] == "dropped"
    assert dropped.json()["task_status"] == "pending"

    response = client.get("/api/v1/export")
    exported = response.json()["daily_plans"]
    assert exported[0]["plan_date"] == "2026-11-11"
    assert [item["status"] for item in exported[0]["items"]] == [
        "completed",
        "deferred",
        "dropped",
    ]
    tasks = {task["id"]: task for task in client.get("/api/v1/tasks").json()}
    assert tasks[task_a["id"]]["status"] == "completed"
    assert tasks[task_b["id"]]["due_date"] == "2026-11-13"

    locked = client.patch(
        f"/api/v1/daily-plans/2026-11-11/items/{item_a['id']}",
        json={"status": "planned"},
    )
    assert locked.status_code == 409
    assert (
        db_session.scalar(select(Task).where(Task.id == UUID(task_c["id"]))).status
        == "pending"
    )


def test_plan_rejects_over_capacity_duplicates_and_foreign_tasks(
    client, test_user, db_session: Session
) -> None:
    _login(client, test_user)
    task = _create_task(client, "Owned task")
    foreign_user = User(email="foreign@example.com", password_hash="unused")
    db_session.add(foreign_user)
    db_session.flush()
    foreign_task = Task(user_id=foreign_user.id, title="Private task")
    db_session.add(foreign_task)
    db_session.commit()

    base = {"capacity_minutes": 30, "energy": "medium"}
    over_capacity = client.put(
        "/api/v1/daily-plans/2026-11-11",
        json={**base, "items": [{"task_id": task["id"], "planned_minutes": 31}]},
    )
    assert over_capacity.status_code == 422

    duplicate = client.put(
        "/api/v1/daily-plans/2026-11-11",
        json={
            **base,
            "items": [
                {"task_id": task["id"], "planned_minutes": 10},
                {"task_id": task["id"], "planned_minutes": 10},
            ],
        },
    )
    assert duplicate.status_code == 422

    foreign = client.put(
        "/api/v1/daily-plans/2026-11-11",
        json={
            **base,
            "items": [{"task_id": str(foreign_task.id), "planned_minutes": 10}],
        },
    )
    assert foreign.status_code == 404

    invalid_capacity = client.put(
        "/api/v1/daily-plans/2026-11-11",
        json={"capacity_minutes": 0, "energy": "medium", "items": []},
    )
    assert invalid_capacity.status_code == 422


def test_reactivating_a_dropped_item_cannot_exceed_capacity(client, test_user) -> None:
    _login(client, test_user)
    task_a = _create_task(client, "Already planned")
    task_b = _create_task(client, "Dropped earlier")
    plan = client.put(
        "/api/v1/daily-plans/2026-11-11",
        json={
            "capacity_minutes": 40,
            "energy": "medium",
            "items": [
                {"task_id": task_a["id"], "planned_minutes": 20},
                {"task_id": task_b["id"], "planned_minutes": 15},
            ],
        },
    ).json()
    first, second = plan["items"]
    assert (
        client.patch(
            f"/api/v1/daily-plans/2026-11-11/items/{first['id']}",
            json={"status": "dropped"},
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/api/v1/daily-plans/2026-11-11/items/{second['id']}",
            json={"status": "dropped"},
        ).status_code
        == 200
    )
    reduced = client.put(
        "/api/v1/daily-plans/2026-11-11",
        json={"capacity_minutes": 30, "energy": "low", "items": []},
    )
    assert reduced.status_code == 200, reduced.text

    assert (
        client.patch(
            f"/api/v1/daily-plans/2026-11-11/items/{first['id']}",
            json={"status": "planned"},
        ).status_code
        == 200
    )
    too_much = client.patch(
        f"/api/v1/daily-plans/2026-11-11/items/{second['id']}",
        json={"status": "planned"},
    )
    assert too_much.status_code == 422


def test_recovery_is_a_preview_and_never_carries_tasks_forward_automatically(
    client, test_user, db_session: Session
) -> None:
    _login(client, test_user)
    older_task = _create_task(client, "Unfinished action", "2026-11-10")
    deferred_task = _create_task(client, "Deferred action", "2026-11-10")
    future_task = _create_task(client, "Not due yet", "2026-11-15")

    first = client.put(
        "/api/v1/daily-plans/2026-11-09",
        json={
            "capacity_minutes": 60,
            "energy": "medium",
            "items": [
                {"task_id": older_task["id"], "planned_minutes": 20},
                {"task_id": deferred_task["id"], "planned_minutes": 15},
                {"task_id": future_task["id"], "planned_minutes": 10},
            ],
        },
    )
    assert first.status_code == 200, first.text
    deferred_item = first.json()["items"][1]
    moved = client.patch(
        f"/api/v1/daily-plans/2026-11-09/items/{deferred_item['id']}",
        json={"status": "deferred", "defer_to": "2026-11-13"},
    )
    assert moved.status_code == 200, moved.text

    # A more recent plan for the same task appears once, with its latest source date.
    second = client.put(
        "/api/v1/daily-plans/2026-11-10",
        json={
            "capacity_minutes": 30,
            "energy": "high",
            "items": [{"task_id": older_task["id"], "planned_minutes": 10}],
        },
    )
    assert second.status_code == 200, second.text

    preview = client.get("/api/v1/daily-plans/2026-11-11/recovery")
    assert preview.status_code == 200, preview.text
    data = preview.json()
    assert data["automatic_carry_forward"] is False
    assert data["penalty_for_missed_day"] is False
    assert [item["title"] for item in data["items"]] == ["Unfinished action"]
    assert data["items"][0]["original_plan_date"] == "2026-11-10"
    assert data["items"][0]["requires_user_choice"] is True
    current_plan = client.get("/api/v1/daily-plans/2026-11-11").json()
    assert current_plan["is_saved"] is False
    assert current_plan["items"] == []
    assert (
        db_session.scalar(
            select(DailyPlan).where(DailyPlan.plan_date == date(2026, 11, 11))
        )
        is None
    )

    chosen = client.put(
        "/api/v1/daily-plans/2026-11-11",
        json={
            "capacity_minutes": 30,
            "energy": "medium",
            "items": [{"task_id": older_task["id"], "planned_minutes": 10}],
        },
    )
    assert chosen.status_code == 200, chosen.text
    refreshed = client.get("/api/v1/daily-plans/2026-11-11/recovery").json()
    assert refreshed["items"] == []

    later_preview = client.get("/api/v1/daily-plans/2026-11-13/recovery").json()
    assert {item["title"] for item in later_preview["items"]} == {
        "Unfinished action",
        "Deferred action",
    }
    assert "Not due yet" not in {item["title"] for item in later_preview["items"]}


def test_daily_plans_are_account_scoped(client, test_user, db_session: Session) -> None:
    _login(client, test_user)
    foreign_user = User(email="other@example.com", password_hash="unused")
    db_session.add(foreign_user)
    db_session.flush()
    foreign_task = Task(user_id=foreign_user.id, title="Private task")
    foreign_plan = DailyPlan(
        user_id=foreign_user.id,
        plan_date=date(2026, 11, 11),
        capacity_minutes=60,
        energy="high",
    )
    foreign_plan.items.append(
        DailyPlanItem(task=foreign_task, position=0, planned_minutes=20)
    )
    db_session.add(foreign_plan)
    db_session.commit()

    response = client.get("/api/v1/daily-plans/2026-11-11")
    assert response.status_code == 200
    assert response.json()["is_saved"] is False
    assert "Private task" not in response.text


def test_deleting_account_cascades_daily_plan_history(
    client, test_user, db_session: Session
) -> None:
    _login(client, test_user)
    task = _create_task(client, "Task to erase with account")
    response = client.put(
        "/api/v1/daily-plans/2026-11-11",
        json={
            "capacity_minutes": 30,
            "energy": "medium",
            "items": [{"task_id": task["id"], "planned_minutes": 10}],
        },
    )
    assert response.status_code == 200, response.text

    deleted = client.request(
        "DELETE",
        "/api/v1/account",
        headers={"X-CSRF-Token": client.cookies.get("lr-csrf")},
        json={
            "current_password": test_user["password"],
            "confirmation": "DELETE MY ACCOUNT",
        },
    )
    assert deleted.status_code == 204, deleted.text
    db_session.expire_all()
    assert db_session.scalar(select(DailyPlan)) is None
    assert db_session.scalar(select(DailyPlanItem)) is None
