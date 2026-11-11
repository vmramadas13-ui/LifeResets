"""Passphrase-encrypted, integrity-checked SQLite backup and restore tools."""

from __future__ import annotations

import argparse
import getpass
import os
import secrets
import sqlite3
import stat
import sys
import tempfile
from contextlib import closing
from pathlib import Path
from urllib.parse import quote

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from sqlalchemy.engine import make_url

from liferesets.settings import get_settings

MAGIC = b"LIFEBAK\x00"
VERSION = b"\x01"
SALT_BYTES = 16
NONCE_BYTES = 12
TAG_BYTES = 16
CHUNK_BYTES = 1024 * 1024
SCRYPT_N = 2**16
SCRYPT_R = 8
SCRYPT_P = 1
MIN_PASSPHRASE_LENGTH = 12
HEADER_BYTES = len(MAGIC) + len(VERSION) + SALT_BYTES + NONCE_BYTES


class BackupError(Exception):
    """A safe, user-displayable backup operation error."""


def _validate_passphrase(passphrase: str) -> bytes:
    if len(passphrase) < MIN_PASSPHRASE_LENGTH:
        raise BackupError(
            f"Passphrase must contain at least {MIN_PASSPHRASE_LENGTH} characters."
        )
    return passphrase.encode("utf-8")


def _derive_key(passphrase: bytes, salt: bytes) -> bytes:
    return Scrypt(
        salt=salt,
        length=32,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
    ).derive(passphrase)


def _temporary_file(parent: Path, prefix: str) -> tuple[int, Path]:
    descriptor, name = tempfile.mkstemp(prefix=prefix, dir=parent)
    os.fchmod(descriptor, stat.S_IRUSR | stat.S_IWUSR)
    return descriptor, Path(name)


def _publish_new_file(temporary: Path, destination: Path) -> None:
    """Atomically publish without replacing an existing file or following links."""
    try:
        os.link(temporary, destination)
    except FileExistsError as error:
        raise BackupError("Destination already exists; choose a new path.") from error
    except OSError as error:
        raise BackupError("Could not safely publish the destination file.") from error
    temporary.unlink()
    try:
        directory_fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError:
        # The file is already durable enough to report success on filesystems
        # that do not support directory fsync.
        pass


def _publish_restored_database(temporary: Path, destination: Path) -> None:
    """Copy a verified SQLite file into a new private destination without overwrite."""
    descriptor = os.open(
        destination,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        stat.S_IRUSR | stat.S_IWUSR,
    )
    try:
        with temporary.open("rb") as reader, os.fdopen(descriptor, "wb") as writer:
            descriptor = -1
            while chunk := reader.read(CHUNK_BYTES):
                writer.write(chunk)
            writer.flush()
            os.fsync(writer.fileno())
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        destination.unlink(missing_ok=True)
        raise
    try:
        directory_fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError:
        pass


def _snapshot_sqlite(source: Path, snapshot: Path) -> None:
    if not source.is_file():
        raise BackupError("Configured SQLite database file was not found.")
    source_uri = f"file:{quote(source.resolve().as_posix())}?mode=ro"
    try:
        with closing(
            sqlite3.connect(source_uri, uri=True, timeout=30)
        ) as source_connection:
            with closing(sqlite3.connect(snapshot, timeout=30)) as snapshot_connection:
                source_connection.backup(snapshot_connection, pages=256, sleep=0.05)
                snapshot_connection.commit()
    except sqlite3.Error as error:
        raise BackupError("Could not create a consistent SQLite snapshot.") from error
    _validate_sqlite(snapshot)


def _validate_sqlite(path: Path) -> None:
    try:
        uri = f"file:{quote(path.resolve().as_posix())}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            if integrity is None or integrity[0] != "ok":
                raise BackupError("SQLite integrity check failed.")
            if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise BackupError("SQLite foreign-key check failed.")
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            if not {"alembic_version", "users"}.issubset(tables):
                raise BackupError("File is not a migrated LifeResets database.")
            version = connection.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()
            if version is None or not version[0]:
                raise BackupError("Database migration version is missing.")
    except sqlite3.Error as error:
        raise BackupError("SQLite database validation failed.") from error


def _encrypt_stream(source: Path, destination: Path, passphrase: bytes) -> None:
    salt = secrets.token_bytes(SALT_BYTES)
    nonce = secrets.token_bytes(NONCE_BYTES)
    header = MAGIC + VERSION + salt + nonce
    encryptor = Cipher(
        algorithms.AES(_derive_key(passphrase, salt)), modes.GCM(nonce)
    ).encryptor()
    encryptor.authenticate_additional_data(header)
    with source.open("rb") as reader, destination.open("wb") as writer:
        writer.write(header)
        while chunk := reader.read(CHUNK_BYTES):
            writer.write(encryptor.update(chunk))
        writer.write(encryptor.finalize())
        writer.write(encryptor.tag)
        writer.flush()
        os.fsync(writer.fileno())


def create_backup(source: Path, destination: Path, passphrase: str) -> Path:
    """Snapshot and encrypt a migrated SQLite database to a new file."""
    raw_passphrase = _validate_passphrase(passphrase)
    source = source.expanduser().resolve()
    destination = destination.expanduser().absolute()
    if not destination.parent.is_dir():
        raise BackupError("Backup destination directory does not exist.")
    if destination.exists():
        raise BackupError("Destination already exists; choose a new path.")

    with tempfile.TemporaryDirectory(prefix="liferesets-snapshot-") as snapshot_dir:
        snapshot = Path(snapshot_dir) / "snapshot.sqlite3"
        _snapshot_sqlite(source, snapshot)
        with tempfile.TemporaryDirectory(
            prefix=".lr-backup-work-", dir=destination.parent
        ) as work_directory:
            work = Path(work_directory)
            encrypted_fd, encrypted = _temporary_file(work, "encrypted-")
            os.close(encrypted_fd)
            _encrypt_stream(snapshot, encrypted, raw_passphrase)
            _publish_new_file(encrypted, destination)
    return destination


def _decrypt_stream(source: Path, destination: Path, passphrase: bytes) -> None:
    try:
        with source.open("rb") as reader:
            header = reader.read(HEADER_BYTES)
            if (
                len(header) != HEADER_BYTES
                or header[: len(MAGIC)] != MAGIC
                or header[len(MAGIC) : len(MAGIC) + 1] != VERSION
            ):
                raise BackupError("File is not a supported LifeResets backup.")
            salt_start = len(MAGIC) + len(VERSION)
            salt = header[salt_start : salt_start + SALT_BYTES]
            nonce = header[salt_start + SALT_BYTES :]
            reader.seek(0, os.SEEK_END)
            file_size = reader.tell()
            encrypted_bytes = file_size - HEADER_BYTES - TAG_BYTES
            if encrypted_bytes < 0:
                raise BackupError("Backup file is incomplete.")
            reader.seek(file_size - TAG_BYTES)
            tag = reader.read(TAG_BYTES)
            reader.seek(HEADER_BYTES)
            decryptor = Cipher(
                algorithms.AES(_derive_key(passphrase, salt)),
                modes.GCM(nonce, tag),
            ).decryptor()
            decryptor.authenticate_additional_data(header)
            with destination.open("wb") as writer:
                remaining = encrypted_bytes
                while remaining:
                    chunk = reader.read(min(CHUNK_BYTES, remaining))
                    if not chunk:
                        raise BackupError("Backup file is incomplete.")
                    remaining -= len(chunk)
                    writer.write(decryptor.update(chunk))
                writer.write(decryptor.finalize())
                writer.flush()
                os.fsync(writer.fileno())
    except InvalidTag as error:
        destination.unlink(missing_ok=True)
        raise BackupError(
            "Passphrase is incorrect or backup data was changed."
        ) from error


def _decrypt_and_validate(source: Path, destination: Path, passphrase: str) -> None:
    raw_passphrase = _validate_passphrase(passphrase)
    source = source.expanduser().resolve()
    if not source.is_file():
        raise BackupError("Backup file was not found.")
    _decrypt_stream(source, destination, raw_passphrase)
    _validate_sqlite(destination)


def restore_backup(backup: Path, destination: Path, passphrase: str) -> Path:
    """Restore an authenticated backup to a new SQLite file only."""
    destination = destination.expanduser().absolute()
    if not destination.parent.is_dir():
        raise BackupError("Restore destination directory does not exist.")
    if destination.exists():
        raise BackupError("Destination already exists; restore never overwrites files.")
    with tempfile.TemporaryDirectory(prefix="liferesets-restore-") as work_directory:
        temporary = Path(work_directory) / "restored.sqlite3"
        descriptor = os.open(
            temporary,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            stat.S_IRUSR | stat.S_IWUSR,
        )
        os.close(descriptor)
        _decrypt_and_validate(backup, temporary, passphrase)
        _publish_restored_database(temporary, destination)
    return destination


def verify_backup(backup: Path, passphrase: str) -> None:
    """Authenticate and integrity-check a backup without keeping restored data."""
    backup = backup.expanduser().resolve()
    if not backup.is_file():
        raise BackupError("Backup file was not found.")
    with tempfile.TemporaryDirectory(prefix="liferesets-verify-") as directory:
        temporary = Path(directory) / "verified.sqlite3"
        descriptor = os.open(
            temporary,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            stat.S_IRUSR | stat.S_IWUSR,
        )
        os.close(descriptor)
        _decrypt_and_validate(backup, temporary, passphrase)


def _configured_sqlite_path() -> Path:
    url = make_url(get_settings().database_url)
    if not url.drivername.startswith("sqlite") or not url.database:
        raise BackupError(
            "This backup command currently supports file-based SQLite databases only."
        )
    if url.database == ":memory:":
        raise BackupError("In-memory SQLite databases cannot be backed up.")
    path = Path(url.database).expanduser()
    return path if path.is_absolute() else Path.cwd() / path


def _read_new_passphrase() -> str:
    first = getpass.getpass("New backup passphrase (12+ characters): ")
    second = getpass.getpass("Confirm backup passphrase: ")
    if first != second:
        raise BackupError("Passphrases did not match.")
    _validate_passphrase(first)
    return first


def _read_passphrase() -> str:
    value = getpass.getpass("Backup passphrase: ")
    _validate_passphrase(value)
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create and restore encrypted LifeResets SQLite backups."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    create_parser = commands.add_parser(
        "create", help="Create an encrypted database snapshot"
    )
    create_parser.add_argument("destination", type=Path)
    restore_parser = commands.add_parser(
        "restore", help="Restore to a new SQLite database file"
    )
    restore_parser.add_argument("backup", type=Path)
    restore_parser.add_argument("destination", type=Path)
    verify_parser = commands.add_parser(
        "verify", help="Verify a backup without retaining restored data"
    )
    verify_parser.add_argument("backup", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            result = create_backup(
                _configured_sqlite_path(), args.destination, _read_new_passphrase()
            )
            print(f"Encrypted backup created: {result}")
        elif args.command == "restore":
            result = restore_backup(args.backup, args.destination, _read_passphrase())
            print(f"Backup restored to new SQLite file: {result}")
        else:
            verify_backup(args.backup, _read_passphrase())
            print("Backup authentication and SQLite integrity checks passed.")
    except (BackupError, OSError) as error:
        print(f"Backup operation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
