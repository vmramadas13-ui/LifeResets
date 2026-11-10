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

## Backup and restore status

Automated encrypted backups and a verified restore command are not implemented. `/api/v1/export` is a user data export, not a database backup or a restore mechanism. Treat backup/restore as a release blocker for hosted or irreplaceable data. Before enabling such a deployment, choose encrypted storage and retention, then test restoring a backup into an isolated environment and reconcile record counts.

## Incident response

For suspected credential exposure, stop the local service, revoke active sessions through account deletion or database administration, rotate any affected secrets, preserve redacted logs, and do not share database files. A hosted deployment requires a separate incident contact path, alerting, and data-breach response plan before launch.
