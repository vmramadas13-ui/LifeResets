# LifeResets

LifeResets is a private, adaptive personal operating system for turning goals into measurable actions. Development follows the staged build sequence and acceptance gates in the master blueprint.

The sanitized PRD requirements catalog and post-build story traceability checklist are maintained in [docs/knowledge/product-requirements.md](docs/knowledge/product-requirements.md). The full PRD stays in the owner's local Downloads folder because it contains sensitive personal measurements.

## Current stage

The repository contains a FastAPI backend and responsive PWA with local account authentication, consent-aware lifecycle records, eight-domain goals and metrics, tasks/habits/evidence, deterministic plan previews, activity-based RPG progression, read-only THE CORE fallback, progress calculations, local calendar export/reminders, and a proposal-only bounded agent. See the PRD traceability checklist for partial and deferred scope.

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
- GET /api/v1/export returns account, profile, consent, audit, goals, metrics, tasks, habits, and evidence data without credentials.
- DELETE /api/v1/account permanently removes the user's profile, sessions, consent records, domain data, and linked audit history.

## Goals and domain data API

- GET /api/v1/domains returns the eight fixed personal domains: career, fitness, finance, discipline, learning, mental wellness, relationships, and lifestyle. Empire remains a cross-domain initiative layer.
- POST /api/v1/goals creates an owned goal with an optional dated target and unit-labelled metrics; GET /api/v1/goals and GET /api/v1/goals/{id} list or retrieve owned goals; PATCH /api/v1/goals/{id} updates goal fields.
- POST /api/v1/goals/{id}/metrics and PATCH /api/v1/metrics/{id} add or update a metric with baseline, target, current value, unit, and optional date.
- GET/POST /api/v1/tasks list or create owned tasks; PATCH /api/v1/tasks/{id} records pending, completed, or skipped status and a UTC completion time.
- GET/POST /api/v1/habits list or create owned habits with a cue, action, schedule, minimum version, and recovery action.
- GET/POST /api/v1/evidence list or add evidence. The public API records evidence as self-reported and unverified; callers cannot mark it verified.

All domain records are scoped to the signed-in account. API creation and changes require the session CSRF token. Dates use ISO calendar dates, and metric values retain their explicitly supplied units.

## THE CORE (initial read-only layer)

POST /api/v1/core/respond accepts an authenticated question and returns a response with context provenance and truncation metadata. It reads only the signed-in user's goals, tasks, habits, and evidence, with limits of 24 records and 6,000 context characters. The current deterministic fallback reports counts; it does not make generated recommendations. There are no tools or write actions. Provider selection and external data processing remain open; see docs/decisions/0002-core-provider-boundary.md.

## Planning and quests (initial preview)

GET /api/v1/plans/preview accepts a start date and a 1–31 day horizon. It returns the signed-in user's pending tasks in that window plus prompts for active goals without tasks. Results are deterministic previews: they are not saved, assigned XP, or dispatched as actions. Creating/editing a plan remains a later step.

## RPG progression (initial rules)

GET /api/v1/rpg/status derives account-owned progression from completed tasks: 10 XP per completed task and 100 XP per level, with first-task and ten-task achievements. The response exposes the formula and frames the level as activity progress, not personal worth. Progression is derived from task state and is not yet a separate event ledger.

## Domain progress intelligence

GET /api/v1/insights/progress compares a metric's current value with its baseline and target using `(current - baseline) / (target - baseline) * 100`. It preserves units and measurement source, returns no percentage when the baseline equals the target, and does not clamp values or make predictions. It is arithmetic only and makes no health or financial recommendations.

## Calendar and reminders

GET /api/v1/notifications/inbox lists pending tasks due from today through the next 31 days. GET /api/v1/calendar.ics downloads the signed-in account's dated tasks as iCalendar events. Both are read-only and account-scoped. The app does not send push/email notifications or sync with an external calendar.

## Bounded agent preview

POST /api/v1/agent/proposals/next-task returns a single task proposal scoped to an active, owned goal. It cannot create records, access external services, or invoke tools. Execution is disabled pending a separate security review and approval design.

## Onboarding, campaigns, and reviews

GET/PATCH /api/v1/onboarding/awakening and /api/v1/onboarding/awakening/{step} provide resumable seven-step progress without collecting onboarding answers. POST/GET /api/v1/campaigns creates and lists 90-calendar-day campaigns; PATCH /api/v1/campaigns/{id} changes status. POST/GET /api/v1/reviews creates and lists weekly/monthly reviews; PATCH /api/v1/reviews/{id} updates review responses or status. Free-text responses require the latest `reflection_storage` consent grant; a later withdrawal blocks new/updated text. Lifecycle records appear in account export and are deleted with the account.

## Operations and safe evolution

The local runbook is [docs/operations.md](docs/operations.md); the project change gates are [docs/decisions/0003-safe-evolution.md](docs/decisions/0003-safe-evolution.md). This is not a production deployment: encrypted backups/restore, monitoring, MFA, password recovery, and deployed rate limiting remain required release gates.

## Web/PWA interface

Open the API root (`/`) for a responsive, installable app shell. The interface supports local sign-in/out, goal creation and listing, plan preview, RPG status, and THE CORE fallback. The service worker caches only static shell files and never caches `/api/` responses. Offline data entry and push notifications are not enabled.

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
