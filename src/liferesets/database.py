"""Database engine and session management."""

import logging
from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from liferesets.settings import get_settings

logger = logging.getLogger(__name__)


def create_database_engine(database_url: str) -> Engine:
    """Create an engine for the configured database URL."""
    connect_args = (
        {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    )
    engine_options = {"pool_pre_ping": True, "connect_args": connect_args}
    if database_url in {"sqlite://", "sqlite:///:memory:"}:
        engine_options["poolclass"] = StaticPool
    engine = create_engine(database_url, **engine_options)

    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def enable_sqlite_foreign_keys(connection, _record) -> None:
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


engine = create_database_engine(get_settings().database_url)
SessionFactory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """Yield a database session for one request."""
    with SessionFactory() as session:
        yield session


def database_is_ready(database_engine: Engine | None = None) -> bool:
    """Return whether a database accepts a simple query."""
    selected_engine = database_engine if database_engine is not None else engine
    try:
        with selected_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        logger.warning("Database readiness probe failed (%s)", type(error).__name__)
        return False
    return True
