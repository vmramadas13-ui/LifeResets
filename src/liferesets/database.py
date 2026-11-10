"""Database engine creation and availability checks."""

import logging

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from liferesets.settings import get_settings

logger = logging.getLogger(__name__)


def create_database_engine(database_url: str) -> Engine:
    """Create an engine for the configured database URL."""
    connect_args = (
        {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    )
    return create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)


engine = create_database_engine(get_settings().database_url)


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
