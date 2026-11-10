from contextlib import nullcontext

from sqlalchemy import select
from sqlalchemy.orm import Session

from liferesets.models import Profile, User


def test_create_user_cli_hashes_password(monkeypatch, db_session: Session) -> None:
    import liferesets.create_user as create_user

    prompts = iter(["vee@example.com"])
    password_prompts = iter(
        [
            "correct horse battery staple number 47",
            "correct horse battery staple number 47",
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: next(prompts))
    monkeypatch.setattr(
        "liferesets.create_user.getpass.getpass", lambda _prompt: next(password_prompts)
    )
    monkeypatch.setattr(
        "liferesets.create_user.SessionFactory", lambda: nullcontext(db_session)
    )

    assert create_user.main() == 0

    user = db_session.scalar(select(User).where(User.email == "vee@example.com"))
    assert user is not None
    assert user.password_hash.startswith("$argon2id$")
    assert user.password_hash != "correct horse battery staple number 47"
    assert db_session.get(Profile, user.id) is not None
