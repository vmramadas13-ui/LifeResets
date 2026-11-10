from uuid import UUID

from sqlalchemy.orm import Session

from liferesets.models import Goal, GoalMetric, User


def _login(client, test_user: dict[str, object]) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": test_user["email"], "password": test_user["password"]},
    )
    assert response.status_code == 200


def test_progress_insights_require_authentication(client) -> None:
    assert client.get("/api/v1/insights/progress").status_code == 401


def test_progress_insights_preserve_units_and_provenance(
    client, test_user, db_session: Session
) -> None:
    _login(client, test_user)
    goal = Goal(user_id=test_user["id"], domain="fitness", title="Walk more")
    goal.metrics.append(
        GoalMetric(
            name="Walking distance",
            unit="km/week",
            baseline_value=2,
            current_value=5,
            target_value=8,
            source="self_report",
        )
    )
    foreign_id = UUID("00000000-0000-0000-0000-000000000001")
    db_session.add_all(
        [goal, User(id=foreign_id, email="other@example.com", password_hash="unused")]
    )
    foreign_goal = Goal(user_id=foreign_id, domain="finance", title="Private")
    db_session.add(foreign_goal)
    db_session.commit()

    response = client.get("/api/v1/insights/progress")
    assert response.status_code == 200
    data = response.json()
    assert len(data["goals"]) == 1
    metric = data["goals"][0]["metrics"][0]
    assert metric["unit"] == "km/week"
    assert metric["progress_percent"] == "50.00"
    assert metric["source"] == "self_report"
    assert "Private" not in response.text


def test_progress_is_undefined_when_baseline_equals_target(
    client, test_user, db_session
) -> None:
    _login(client, test_user)
    goal = Goal(user_id=test_user["id"], domain="learning", title="Learn")
    goal.metrics.append(
        GoalMetric(
            name="score",
            unit="points",
            baseline_value=5,
            current_value=5,
            target_value=5,
        )
    )
    db_session.add(goal)
    db_session.commit()
    metric = client.get("/api/v1/insights/progress").json()["goals"][0]["metrics"][0]
    assert metric["progress_percent"] is None
