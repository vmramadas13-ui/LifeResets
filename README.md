# LifeResets

LifeResets is a private, adaptive personal operating system for turning goals into measurable actions. Development follows the staged build sequence and acceptance gates in the master blueprint.

## Current stage

The repository contains the initial FastAPI application, environment-based settings, and a process health endpoint. Database connections and migration scaffolding are in place. Domain tables, identity, and product features are still pending.

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
