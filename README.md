# LifeResets

LifeResets is a private, adaptive personal operating system for turning goals into measurable actions. Development follows the staged build sequence and acceptance gates in the master blueprint.

## Current stage

The repository contains the FastAPI application, database migrations, local account authentication, profile and consent APIs, account data export/deletion, and minimal audit events. Domain features are still pending.

## Requirements

- Git
- Python 3.12
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

## Set up locally

From the repository root, create the project environment and install the exact dependencies recorded in `uv.lock`:

```bash
uv sync --locked --all-groups
```

The project virtual environment is created at `.venv/`. Use `uv run` for project commands so they run in that environment. Copy `.env.example` to `.env` only if you need local settings overrides.

## Run the API locally

```bash
uv run uvicorn liferesets.main:app --reload
```

The liveness endpoint is `http://127.0.0.1:8000/health`; readiness, including a database connection check, is `http://127.0.0.1:8000/ready`. Interactive API docs are at `http://127.0.0.1:8000/docs`.

Local development defaults to SQLite, so no database service is needed. The database URL is configurable with `LIFERESETS_DATABASE_URL`; use a PostgreSQL URL with the `postgresql+psycopg` driver when connecting to PostgreSQL. The local-versus-deployment database strategy remains open for a later decision. API errors use a consistent JSON envelope, validation responses omit submitted values, and the configured log level is available through `LIFERESETS_LOG_LEVEL`.

## Create the first local account

After applying migrations, create an account from the terminal. Password input is hidden and never passed as a command-line argument:

~~~bash
uv run --locked python -m liferesets.create_user
~~~

The account flow uses Argon2id password hashes, revocable server-side sessions, HttpOnly SameSite cookies, and a session-bound CSRF token. The auth choice and remaining security work are recorded in docs/decisions/0001-local-identity.md. Protected data belongs to the signed-in account. Account deletion requires the current password, a CSRF token, and the exact confirmation phrase DELETE MY ACCOUNT.

This is a local-first account foundation. MFA, password recovery, and deployed login rate limiting are not implemented yet; keep the API bound to localhost until those controls and deployment security are reviewed.

## Identity and privacy API

- POST /api/v1/auth/login, GET /api/v1/auth/me, and POST /api/v1/auth/logout manage sign-in.
- GET and PATCH /api/v1/profile read or update the signed-in profile.
- GET and POST /api/v1/consents inspect or append consent records. Each grant or withdrawal is a new record.
- GET /api/v1/audit lists minimal account events.
- GET /api/v1/export returns account, profile, consent, and audit data without credentials.
- DELETE /api/v1/account permanently removes the user's profile, sessions, consent records, and linked audit history.

For state-changing requests, read the lr-csrf cookie and send its value in the X-CSRF-Token header. The session cookie is HttpOnly.

## Database migrations

Apply migrations with:

```bash
uv run --locked alembic upgrade head
```

To roll the schema back to its base revision:

```bash
uv run --locked alembic downgrade base
```

## Run checks

```bash
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
```

GitHub Actions runs the same checks for pushes and pull requests.

## Development workflow

1. Start a focused branch from `main` for each change.
2. Keep implementation and tests together, and run all checks above.
3. Review the diff for secrets, personal data, and unintended changes before committing.

Do not commit `.env` files, credentials, or personal exports. `.env.example` contains safe defaults for local configuration; do not put credentials or personal data in it.

## Project layout

```text
.github/workflows/  Continuous integration
src/liferesets/     Python application package
.env.example        Local settings template
tests/              Automated tests
```
