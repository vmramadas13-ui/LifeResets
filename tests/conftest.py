from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from liferesets import models as _models  # noqa: F401
from liferesets.base import Base
from liferesets.database import create_database_engine, get_db
from liferesets.main import app
from liferesets.models import Profile, User
from liferesets.security import hash_password


@pytest.fixture
def db_engine():
    engine = create_database_engine("sqlite://")
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(db_engine) -> Generator[Session, None, None]:
    test_session_factory = sessionmaker(
        bind=db_engine, autoflush=False, expire_on_commit=False
    )
    with test_session_factory() as session:
        yield session


@pytest.fixture
def client(db_engine) -> Generator[TestClient, None, None]:
    test_session_factory = sessionmaker(
        bind=db_engine, autoflush=False, expire_on_commit=False
    )

    def override_get_db() -> Generator[Session, None, None]:
        with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def test_user(db_session: Session) -> dict[str, object]:
    email = "vee@example.com"
    password = "correct horse battery staple number 47"
    user = User(email=email, password_hash=hash_password(password))
    user.profile = Profile(display_name="Example User", timezone="Asia/Kolkata")
    db_session.add(user)
    db_session.commit()
    return {"id": user.id, "email": email, "password": password}
