from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from liferesets.models import AuditEvent, Goal, User


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
