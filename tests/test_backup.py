import stat
from datetime import date
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from liferesets.backup import (
    BackupError,
    _configured_sqlite_path,
    create_backup,
    main,
    restore_backup,
    verify_backup,
)
from liferesets.database import create_database_engine
from liferesets.models import Campaign, Evidence, Goal, GoalMetric, Review, Task, User
from liferesets.settings import get_settings

ROOT = Path(__file__).resolve().parents[1]
PASSPHRASE = "correct horse backup phrase 29"


def _make_migrated_database(path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{path}"
    monkeypatch.setenv("LIFERESETS_DATABASE_URL", database_url)
    get_settings.cache_clear()
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    get_settings.cache_clear()


def _insert_linked_records(path: Path) -> None:
    engine = create_database_engine(f"sqlite:///{path}")
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        user = User(email="backup@example.com", password_hash="test-only-hash")
        goal = Goal(
            user=user,
            domain="learning",
            title="Private linked goal",
            metrics=[GoalMetric(name="Practice time", unit="minutes", target_value=90)],
        )
        session.add(user)
        session.add(goal)
        session.flush()
        task = Task(user_id=user.id, goal_id=goal.id, title="Private linked task")
        session.add(task)
        session.flush()
        session.add_all(
            [
                Campaign(
                    user_id=user.id,
                    title="Quarter plan",
                    objective="Build a project",
                    starts_on=date(2026, 1, 1),
                    ends_on=date(2026, 3, 31),
                ),
                Review(
                    user_id=user.id,
                    cadence="weekly",
                    period_start=date(2026, 1, 5),
                    period_end=date(2026, 1, 11),
                    responses={"wins": "Private reflection"},
                ),
                Evidence(
                    user_id=user.id,
                    goal_id=goal.id,
                    task_id=task.id,
                    summary="Private evidence",
                ),
            ]
        )
        session.commit()
    engine.dispose()


def test_encrypted_backup_restore_preserves_linked_data_and_private_file_mode(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "source.sqlite3"
    backup_file = tmp_path / "life.lrbak"
    restored = tmp_path / "restored.sqlite3"
    _make_migrated_database(source, monkeypatch)
    _insert_linked_records(source)

    create_backup(source, backup_file, PASSPHRASE)
    encrypted = backup_file.read_bytes()
    assert b"backup@example.com" not in encrypted
    assert b"Private linked goal" not in encrypted
    assert stat.S_IMODE(backup_file.stat().st_mode) == 0o600
    verify_backup(backup_file, PASSPHRASE)
    restore_backup(backup_file, restored, PASSPHRASE)
    assert stat.S_IMODE(restored.stat().st_mode) == 0o600

    engine = create_database_engine(f"sqlite:///{restored}")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        user = session.scalar(select(User).where(User.email == "backup@example.com"))
        assert user is not None
        goal = session.scalar(select(Goal).where(Goal.user_id == user.id))
        task = session.scalar(select(Task).where(Task.user_id == user.id))
        evidence = session.scalar(select(Evidence).where(Evidence.user_id == user.id))
        review = session.scalar(select(Review).where(Review.user_id == user.id))
        assert (
            goal is not None
            and task is not None
            and evidence is not None
            and review is not None
        )
        assert task.goal_id == goal.id
        assert evidence.task_id == task.id and evidence.goal_id == goal.id
        assert review.responses["wins"] == "Private reflection"
        assert session.scalar(select(func.count()).select_from(GoalMetric)) == 1
        assert session.scalar(select(func.count()).select_from(Campaign)) == 1
    engine.dispose()


def test_wrong_passphrase_and_tampering_never_publish_a_restore(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "source.sqlite3"
    backup_file = tmp_path / "life.lrbak"
    target = tmp_path / "restored.sqlite3"
    _make_migrated_database(source, monkeypatch)
    _insert_linked_records(source)
    create_backup(source, backup_file, PASSPHRASE)

    with pytest.raises(BackupError, match="Passphrase is incorrect"):
        restore_backup(backup_file, target, "a completely wrong passphrase")
    assert not target.exists()

    tampered = tmp_path / "tampered.lrbak"
    contents = bytearray(backup_file.read_bytes())
    contents[len(contents) // 2] ^= 1
    tampered.write_bytes(contents)
    with pytest.raises(BackupError, match="Passphrase is incorrect"):
        verify_backup(tampered, PASSPHRASE)
    assert not target.exists()


def test_restore_never_overwrites_destination_and_backup_requires_passphrase(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "source.sqlite3"
    backup_file = tmp_path / "life.lrbak"
    target = tmp_path / "existing.sqlite3"
    _make_migrated_database(source, monkeypatch)
    create_backup(source, backup_file, PASSPHRASE)
    target.write_bytes(b"keep this file")

    with pytest.raises(BackupError, match="never overwrites"):
        restore_backup(backup_file, target, PASSPHRASE)
    assert target.read_bytes() == b"keep this file"
    with pytest.raises(BackupError, match="at least 12"):
        create_backup(source, tmp_path / "short-passphrase.lrbak", "short")


def test_interactive_cli_create_verify_restore_round_trip(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "source.sqlite3"
    backup_file = tmp_path / "interactive.lrbak"
    restored = tmp_path / "interactive-restore.sqlite3"
    _make_migrated_database(source, monkeypatch)
    _insert_linked_records(source)
    monkeypatch.setenv("LIFERESETS_DATABASE_URL", f"sqlite:///{source}")
    get_settings.cache_clear()
    responses = iter([PASSPHRASE, PASSPHRASE, PASSPHRASE, PASSPHRASE, PASSPHRASE])
    monkeypatch.setattr(
        "liferesets.backup.getpass.getpass", lambda _prompt: next(responses)
    )

    assert main(["create", str(backup_file)]) == 0
    assert "Encrypted backup created" in capsys.readouterr().out
    assert main(["verify", str(backup_file)]) == 0
    assert "integrity checks passed" in capsys.readouterr().out
    assert main(["restore", str(backup_file), str(restored)]) == 0
    assert "restored to new SQLite file" in capsys.readouterr().out
    get_settings.cache_clear()


def test_configured_postgresql_backup_is_rejected_until_supported(monkeypatch) -> None:
    monkeypatch.setenv(
        "LIFERESETS_DATABASE_URL",
        "postgresql+psycopg://user:secret@localhost/liferesets",
    )
    get_settings.cache_clear()
    try:
        with pytest.raises(BackupError, match="file-based SQLite"):
            _configured_sqlite_path()
    finally:
        get_settings.cache_clear()
