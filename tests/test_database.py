import uuid
from datetime import UTC, date, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    Uuid,
    create_engine,
    insert,
    inspect,
    select,
    text,
)

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
        assert revision == "fe1c02ab2dd3"
        assert {
            "users",
            "profiles",
            "auth_sessions",
            "consent_records",
            "audit_events",
            "goals",
            "goal_metrics",
            "tasks",
            "habits",
            "evidence",
            "campaigns",
            "onboarding_steps",
            "reviews",
            "review_follow_ups",
            "daily_plans",
            "daily_plan_items",
            "progression_settings",
            "progression_events",
            "skills",
            "skill_evidence",
            "agent_actions",
            "metric_measurements",
            "habit_check_ins",
            "awakening_baselines",
            "awakening_baseline_goal_links",
            "awakening_assessments",
            "domain_subareas",
            "daily_plan_busy_windows",
            "task_reschedule_events",
            "quests",
            "quest_steps",
            "campaign_arcs",
            "campaign_checkpoints",
            "campaign_scope_changes",
            "campaign_retrospectives",
            "daily_reflections",
        }.issubset(inspect(engine).get_table_names())
        assert "answer" in {
            column["name"] for column in inspect(engine).get_columns("onboarding_steps")
        }
        assert "confidence" in {
            column["name"] for column in inspect(engine).get_columns("goal_metrics")
        }
        assert {
            "weekdays",
            "interval_days",
            "start_date",
            "end_date",
            "reminder_preference",
        }.issubset({column["name"] for column in inspect(engine).get_columns("habits")})
        assert "subarea_id" in {
            column["name"] for column in inspect(engine).get_columns("goals")
        }
        assert {"day_start_time", "day_end_time"}.issubset(
            {column["name"] for column in inspect(engine).get_columns("daily_plans")}
        )

        command.downgrade(config, "base")
        assert not {
            "users",
            "profiles",
            "auth_sessions",
            "consent_records",
            "audit_events",
            "goals",
            "goal_metrics",
            "tasks",
            "habits",
            "evidence",
            "campaigns",
            "onboarding_steps",
            "reviews",
            "review_follow_ups",
            "daily_plans",
            "daily_plan_items",
            "progression_settings",
            "progression_events",
            "skills",
            "skill_evidence",
            "agent_actions",
            "metric_measurements",
            "habit_check_ins",
            "awakening_baselines",
            "awakening_baseline_goal_links",
            "awakening_assessments",
            "domain_subareas",
            "daily_plan_busy_windows",
            "task_reschedule_events",
            "quests",
            "quest_steps",
            "campaign_arcs",
            "campaign_checkpoints",
            "campaign_scope_changes",
            "campaign_retrospectives",
            "daily_reflections",
        }.intersection(inspect(engine).get_table_names())
        with engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).first()
        assert revision is None
    finally:
        engine.dispose()
        get_settings.cache_clear()


def test_campaign_migration_backfills_weekly_arcs(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'campaign-backfill.db'}"
    monkeypatch.setenv("LIFERESETS_DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config(str(ROOT / "alembic.ini"))
    engine = create_engine(database_url)
    user_id = uuid.uuid4()
    campaign_id = uuid.uuid4()
    created_at = datetime.now(UTC)

    try:
        command.upgrade(config, "42d916f7bca0")
        metadata = MetaData()
        users = Table("users", metadata, autoload_with=engine)
        campaigns = Table("campaigns", metadata, autoload_with=engine)
        with engine.begin() as connection:
            connection.execute(
                insert(users).values(
                    id=user_id.hex,
                    email="campaign-backfill@example.com",
                    password_hash="unused",
                    is_active=True,
                    created_at=created_at,
                )
            )
            connection.execute(
                insert(campaigns).values(
                    id=campaign_id.hex,
                    user_id=user_id.hex,
                    title="Existing campaign",
                    objective="Keep the original plan",
                    starts_on=date(2026, 1, 1),
                    ends_on=date(2026, 3, 31),
                    status="active",
                    created_at=created_at,
                )
            )
        command.upgrade(config, "head")
        arcs = Table("campaign_arcs", MetaData(), autoload_with=engine)
        with engine.connect() as connection:
            rows = connection.execute(
                select(arcs)
                .where(arcs.c.campaign_id == campaign_id.hex)
                .order_by(arcs.c.week_number)
            ).all()
        assert len(rows) == 13
        assert rows[0].starts_on.isoformat() == "2026-01-01"
        assert rows[-1].ends_on.isoformat() == "2026-03-31"
    finally:
        engine.dispose()
        get_settings.cache_clear()


def test_database_readiness_uses_a_simple_query() -> None:
    engine = create_database_engine("sqlite://")

    try:
        assert database_is_ready(engine) is True
    finally:
        engine.dispose()


def test_progression_migration_preserves_xp_for_preexisting_completed_tasks(
    tmp_path: Path, monkeypatch
) -> None:
    database_url = f"sqlite:///{tmp_path / 'progression-backfill.db'}"
    monkeypatch.setenv("LIFERESETS_DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config(str(ROOT / "alembic.ini"))
    engine = create_engine(database_url)
    user_id = uuid.uuid4()
    task_id = uuid.uuid4()
    created_at = datetime.now(UTC)
    metadata = MetaData()
    users = Table(
        "users",
        metadata,
        Column("id", Uuid()),
        Column("email", String(320)),
        Column("password_hash", String(255)),
        Column("is_active", Boolean()),
        Column("created_at", DateTime(timezone=True)),
    )
    tasks = Table(
        "tasks",
        metadata,
        Column("id", Uuid()),
        Column("user_id", Uuid()),
        Column("goal_id", Uuid(), nullable=True),
        Column("title", String(160)),
        Column("description", String(), nullable=True),
        Column("due_date", DateTime(), nullable=True),
        Column("status", String(16)),
        Column("completed_at", DateTime(timezone=True), nullable=True),
        Column("created_at", DateTime(timezone=True)),
    )

    try:
        command.upgrade(config, "28aa37bcab28")
        with engine.begin() as connection:
            connection.execute(
                insert(users).values(
                    id=user_id,
                    email="ledger-migration@example.com",
                    password_hash="unused",
                    is_active=True,
                    created_at=created_at,
                )
            )
            connection.execute(
                insert(tasks).values(
                    id=task_id,
                    user_id=user_id,
                    goal_id=None,
                    title="Legacy completed task",
                    description=None,
                    due_date=None,
                    status="completed",
                    completed_at=created_at,
                    created_at=created_at,
                )
            )
        command.upgrade(config, "head")
        with engine.connect() as connection:
            row = connection.execute(
                select(
                    text("event_type"),
                    text("xp_delta"),
                    text("task_id"),
                ).select_from(text("progression_events"))
            ).one()
        assert row.event_type == "task_completed"
        assert row.xp_delta == 10
        assert str(task_id).replace("-", "") in str(row.task_id).replace("-", "")
    finally:
        engine.dispose()
        get_settings.cache_clear()
