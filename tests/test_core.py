from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from liferesets.core import CoreContext, answer_read_only
from liferesets.models import Goal, User


def _login(client, test_user: dict[str, object]) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": test_user["email"], "password": test_user["password"]},
    )
    assert response.status_code == 200
    client.headers.update({"X-CSRF-Token": client.cookies.get("lr-csrf")})


def test_core_requires_auth_and_csrf(client, test_user) -> None:
    assert (
        client.post("/api/v1/core/respond", json={"question": "What next?"}).status_code
        == 401
    )
    _login(client, test_user)
    client.headers.pop("X-CSRF-Token")
    assert (
        client.post("/api/v1/core/respond", json={"question": "What next?"}).status_code
        == 403
    )


def test_core_fallback_is_account_scoped_and_provenance_tagged(
    client, test_user, db_session: Session
) -> None:
    _login(client, test_user)
    other_user_id = UUID("00000000-0000-0000-0000-000000000001")
    db_session.add_all(
        [
            User(id=other_user_id, email="another@example.com", password_hash="unused"),
            Goal(user_id=test_user["id"], domain="learning", title="Study algebra"),
            Goal(user_id=other_user_id, domain="career", title="Private foreign goal"),
        ]
    )
    db_session.commit()
    response = client.post("/api/v1/core/respond", json={"question": "  What  next?  "})
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "fallback"
    assert data["answer"] == "Saved context: 1 goal."
    assert data["provenance"] == ["user_created_goal"]
    assert data["read_only"] is True
    assert "Private foreign" not in response.text
    assert db_session.scalar(select(func.count()).select_from(Goal)) == 2


def test_adapter_gets_bounded_context_without_action_capability(
    db_session: Session, test_user
) -> None:
    db_session.add(
        Goal(user_id=test_user["id"], domain="career", title="Build a portfolio")
    )
    db_session.commit()

    class InspectingAdapter:
        def respond(self, question: str, context: CoreContext) -> str:
            assert question == "Suggest a first step"
            assert len(context.records) == 1
            assert context.records[0]["provenance"] == "user_created_goal"
            assert not hasattr(self, "tools")
            return "Choose one small portfolio piece."

    result = answer_read_only(
        db_session, test_user["id"], "Suggest a first step", InspectingAdapter()
    )
    assert result["answer"] == "Choose one small portfolio piece."
    assert result["mode"] == "adapter"
    assert result["read_only"] is True
