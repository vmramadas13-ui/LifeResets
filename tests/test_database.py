from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from liferesets.database import create_database_engine, database_is_ready
from liferesets.settings import get_settings

ROOT = Path(__file__).resolve().parents[1]


def test_migration_upgrade_and_rollback(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'migration-test.db'}"
    monkeypatch.setenv("LIFERESETS_DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config(str(ROOT / "alembic.ini"))
    engine = create_engine(database_url)

    try:
        command.upgrade(config, "head")
        with engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
        assert revision == "60c2191796d2"
        assert {
            "users",
            "profiles",
            "auth_sessions",
            "consent_records",
            "audit_events",
        }.issubset(inspect(engine).get_table_names())

        command.downgrade(config, "base")
        assert not {
            "users",
            "profiles",
            "auth_sessions",
            "consent_records",
            "audit_events",
        }.intersection(inspect(engine).get_table_names())
        with engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).first()
        assert revision is None
    finally:
        engine.dispose()
        get_settings.cache_clear()


def test_database_readiness_uses_a_simple_query() -> None:
    engine = create_database_engine("sqlite://")

    try:
        assert database_is_ready(engine) is True
    finally:
        engine.dispose()
