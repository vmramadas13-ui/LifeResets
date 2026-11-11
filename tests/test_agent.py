from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from liferesets.models import AgentAction, AuditEvent, Goal, Task, User


def _login(client, test_user: dict[str, object]) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": test_user["email"], "password": test_user["password"]},
    )
    assert response.status_code == 200
    client.headers.update({"X-CSRF-Token": client.cookies.get("lr-csrf")})


def test_agent_proposals_require_authentication(client) -> None:
    assert (
        client.post(
            "/api/v1/agent/proposals/next-task", json={"goal_id": str(UUID(int=1))}
        ).status_code
        == 401
    )


def test_agent_proposal_is_scoped_and_performs_no_action(
    client, test_user, db_session: Session
) -> None:
    _login(client, test_user)
    goal = Goal(user_id=test_user["id"], domain="learning", title="Learn SQL")
    other_id = UUID("00000000-0000-0000-0000-000000000001")
    db_session.add_all(
        [goal, User(id=other_id, email="other@example.com", password_hash="unused")]
    )
    foreign = Goal(user_id=other_id, domain="career", title="Private")
    db_session.add(foreign)
    db_session.commit()
    task_count = db_session.scalar(select(func.count()).select_from(Goal))
    audit_count = db_session.scalar(select(func.count()).select_from(AuditEvent))

    response = client.post(
        "/api/v1/agent/proposals/next-task", json={"goal_id": str(goal.id)}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["proposal"]["action"] == "create_task"
    assert data["requires_explicit_approval"] is True
    assert data["execution_available"] is False
    assert data["writes_performed"] is False
    assert data["external_access"] is False
    assert data["tools_available"] == []
    assert db_session.scalar(select(func.count()).select_from(Goal)) == task_count
    assert (
        db_session.scalar(select(func.count()).select_from(AuditEvent)) == audit_count
    )

    hidden = client.post(
        "/api/v1/agent/proposals/next-task", json={"goal_id": str(foreign.id)}
    )
    assert hidden.status_code == 404


def test_agent_task_action_requires_approval_and_is_idempotent(
    client, test_user, db_session: Session
) -> None:
    _login(client, test_user)
    goal = Goal(user_id=test_user["id"], domain="learning", title="Learn Python")
    db_session.add(goal)
    db_session.commit()

    proposal = client.post(
        "/api/v1/agent/actions",
        json={"goal_id": str(goal.id), "task_title": "Practice one loop"},
    )
    assert proposal.status_code == 201
    action = proposal.json()
    assert action["status"] == "proposed"
    assert action["risk_tier"] == "local_reversible"
    assert action["requires_explicit_approval"] is True
    assert action["external_access"] is False
    assert db_session.scalar(select(func.count()).select_from(Task)) == 0

    approval_path = f"/api/v1/agent/actions/{action['id']}/approve"
    csrf = client.headers.pop("X-CSRF-Token")
    assert client.post(approval_path).status_code == 403
    assert db_session.scalar(select(func.count()).select_from(Task)) == 0
    client.headers["X-CSRF-Token"] = csrf
    approved = client.post(approval_path)
    assert approved.status_code == 200
    task_id = approved.json()["task"]["id"]
    assert approved.json()["task"]["title"] == "Practice one loop"
    repeated_approval = client.post(approval_path)
    assert repeated_approval.status_code == 200
    assert repeated_approval.json()["task"]["id"] == task_id
    assert db_session.scalar(select(func.count()).select_from(Task)) == 1

    undo_path = f"/api/v1/agent/actions/{action['id']}/undo"
    undone = client.post(undo_path)
    assert undone.status_code == 200
    assert undone.json()["status"] == "undone"
    task = db_session.get(Task, UUID(task_id))
    assert task is not None and task.status == "skipped"
    assert client.post(undo_path).status_code == 200
    assert client.get("/api/v1/export").json()["agent_actions"][0]["status"] == "undone"


def test_agent_reject_and_foreign_approval_do_not_create_tasks(
    client, test_user, db_session: Session
) -> None:
    _login(client, test_user)
    goal = Goal(user_id=test_user["id"], domain="career", title="Build portfolio")
    foreign_user = User(
        id=UUID("00000000-0000-0000-0000-000000000007"),
        email="agent-other@example.com",
        password_hash="unused",
    )
    db_session.add_all([goal, foreign_user])
    foreign_goal = Goal(user_id=foreign_user.id, domain="career", title="Private goal")
    db_session.add(foreign_goal)
    db_session.commit()
    foreign_action = AgentAction(
        user_id=foreign_user.id,
        goal_id=foreign_goal.id,
        proposal={"title": "Private task", "goal_title": "Private goal"},
    )
    db_session.add(foreign_action)
    db_session.commit()

    assert (
        client.post(
            "/api/v1/agent/actions",
            json={"goal_id": str(foreign_goal.id), "task_title": "Access private goal"},
        ).status_code
        == 404
    )
    action = client.post(
        "/api/v1/agent/actions",
        json={"goal_id": str(goal.id), "task_title": "Draft one portfolio note"},
    ).json()
    assert (
        client.post(f"/api/v1/agent/actions/{UUID(int=999)}/approve").status_code == 404
    )
    assert (
        client.post(f"/api/v1/agent/actions/{foreign_action.id}/approve").status_code
        == 404
    )
    rejected = client.post(f"/api/v1/agent/actions/{action['id']}/reject")
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert (
        client.post(f"/api/v1/agent/actions/{action['id']}/approve").status_code == 409
    )
    assert db_session.scalar(select(func.count()).select_from(Task)) == 0
    assert client.get("/api/v1/agent/actions").json()[0]["id"] == action["id"]


def test_agent_action_undo_requires_unplanned_pending_task(
    client, test_user, db_session
):
    _login(client, test_user)
    goal = Goal(user_id=test_user["id"], domain="learning", title="Study")
    db_session.add(goal)
    db_session.commit()
    action = client.post(
        "/api/v1/agent/actions",
        json={"goal_id": str(goal.id), "task_title": "Review a lesson"},
    ).json()
    approved = client.post(f"/api/v1/agent/actions/{action['id']}/approve").json()
    task = db_session.get(Task, UUID(approved["task"]["id"]))
    db_session.add(Task(user_id=test_user["id"], title="Anchor task"))
    db_session.commit()
    assert task is not None
    from liferesets.models import DailyPlan, DailyPlanItem

    plan = DailyPlan(
        user_id=test_user["id"],
        plan_date=date(2026, 11, 11),
        capacity_minutes=30,
        energy="medium",
    )
    db_session.add(plan)
    db_session.flush()
    db_session.add(
        DailyPlanItem(
            plan_id=plan.id,
            task_id=task.id,
            position=0,
            planned_minutes=10,
            status="dropped",
        )
    )
    db_session.commit()
    response = client.post(f"/api/v1/agent/actions/{action['id']}/undo")
    assert response.status_code == 409
    assert (
        response.json()["error"]["message"]
        == "Remove this action from its daily plans before undoing it."
    )
