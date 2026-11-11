# LifeResets operations runbook

## Current deployment boundary

This repository is a local development build. Do not expose it to a public network or put real sensitive health/financial data in a deployed instance. Production hosting is not configured. MFA, password recovery, deployed authentication rate limiting, encrypted backups, restore rehearsal, monitoring/alerts, and secure secret management must be completed before a hosted rollout.

## Local start and checks

1. Install locked dependencies with `uv sync --locked --all-groups`.
2. Apply schema changes with `uv run --locked alembic upgrade head`.
3. Create a local account with `uv run --locked python -m liferesets.create_user`.
4. Run locally with `uv run --locked uvicorn liferesets.main:app --host 127.0.0.1 --port 8000`.
5. Check `/health` for process liveness and `/ready` for database connectivity.
6. Before committing, run `uv run --locked pytest`, `uv run --locked ruff check .`, `uv run --locked ruff format --check .`, and `git diff --check`.

Keep `.env` and database files local. Never include credentials, personal exports, or populated databases in commits or issue reports. Logs must not include passwords, session tokens, request bodies, CORE questions, or private measurements.

## Release procedure

Use a focused branch. Review schema and data export/deletion changes together. Require local checks and the GitHub Actions checks to pass. Merge only a green branch. Confirm the target revision and documented rollback behavior before applying migrations to any user data. Run the release against a disposable copy first.

## Encrypted SQLite backup and restore

The CLI makes a consistent SQLite snapshot, derives a 256-bit key from the passphrase with Scrypt (`n=2^16`, `r=8`, `p=1`), and encrypts/authenticates it with AES-256-GCM. The backup file has owner-only permissions. Snapshot and restore use a temporary owner-only directory; the final restored SQLite file is unencrypted and has owner-only permissions. Keep the Mac's disk encryption enabled and restore only into a trusted local folder. Restore verifies authentication and database integrity before copying to a new destination. Use a unique destination path; the CLI never overwrites an existing file. The passphrase is entered interactively and is not stored with the backup. Keep it in a password manager: a lost passphrase cannot be recovered.

```bash
uv run --locked python -m liferesets.backup create "/path/to/new/liferesets-2026-11-11.lrbak"
uv run --locked python -m liferesets.backup verify "/path/to/new/liferesets-2026-11-11.lrbak"
uv run --locked python -m liferesets.backup restore "/path/to/new/liferesets-2026-11-11.lrbak" "/path/to/new/restore-test.sqlite3"
```

Backup creation reads the configured file-based SQLite database (`LIFERESETS_DATABASE_URL`, default `./liferesets.db`). Restore writes only to a new SQLite file, verifies the authentication tag, SQLite integrity, foreign keys, and migration marker, and preserves linked rows. It does not replace the configured database. To run a restored database, point `LIFERESETS_DATABASE_URL` at that new file; review its migration revision before any migration.

PostgreSQL backup/restore, scheduled backups, automated retention/rotation, and restore monitoring are not implemented. `/api/v1/export` remains a user data export, not a database backup. Hosted deployment remains blocked until backups are automated, stored separately, and a documented restore drill reconciles record counts and checksums.

## Incident response

For suspected credential exposure, stop the local service, revoke active sessions through account deletion or database administration, rotate any affected secrets, preserve redacted logs, and do not share database files. A hosted deployment requires a separate incident contact path, alerting, and data-breach response plan before launch.
