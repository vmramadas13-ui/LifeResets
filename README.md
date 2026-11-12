# LifeResets

LifeResets is a private, adaptive personal operating system for turning goals into measurable actions. The user has clarified that iPhone is the primary device, with full Mac support. Development follows the staged build sequence and acceptance gates in the master blueprint.

The sanitized PRD requirements catalog and post-build story traceability checklist are maintained in [docs/knowledge/product-requirements.md](docs/knowledge/product-requirements.md). The full PRD stays in the owner's local Downloads folder because it contains sensitive personal measurements.

## Current stage

The repository contains a FastAPI backend and responsive PWA with local account authentication, consent-aware lifecycle records, eight configurable life areas, goals with confidence-labelled dated metric history, tasks/habits/evidence, persistent capacity-aware daily plans with user-controlled recovery suggestions, deterministic plan previews, a versioned and correctable XP ledger, rank thresholds, user-defined skills with self-reported evidence, a Chronicle, read-only THE CORE fallback, progress calculations, local calendar export/reminders, and a single-action agent flow that requires explicit approval and can be undone when unused. The UI follows the Inkpop visual direction and includes iPhone bottom navigation plus browser-persisted light/dark, reduced-motion, and standard-language controls. Voice input only uses browser-confirmed on-device recognition; if unavailable, use iPhone keyboard dictation. Spoken replies require a tap. See [visual requirements](docs/design/visual-requirements.md) and the PRD traceability checklist for scope and gaps.

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
- GET /api/v1/export returns account, profile, consent, audit, goals, metrics, tasks, habits, evidence, lifecycle records, and daily plans without credentials.
- DELETE /api/v1/account permanently removes the user's profile, sessions, consent records, domain data, and linked audit history.

## Goals and domain data API

- GET /api/v1/domains returns the signed-in user's names, order, and visibility for the eight built-in areas: career, fitness, finance, discipline, learning, mental wellness, relationships, and lifestyle. PUT /api/v1/domains/settings saves these preferences. Hiding an area prevents new goals in it but preserves existing goals. Empire remains a cross-domain initiative layer.
- POST /api/v1/goals creates an owned goal with an optional dated target and unit-labelled metrics; GET /api/v1/goals and GET /api/v1/goals/{id} list or retrieve owned goals; PATCH /api/v1/goals/{id} updates goal fields.
- POST /api/v1/goals/{id}/metrics and PATCH /api/v1/metrics/{id} add or update a metric with baseline, target, current value, unit, confidence, and optional date. POST /api/v1/metrics/{id}/measurements appends a dated value; GET /api/v1/metrics/{id}/history returns that metric's account-owned history. Goal exports include the measurement history.
- GET/POST /api/v1/tasks list or create owned tasks; PATCH /api/v1/tasks/{id} records pending, completed, or skipped status and a UTC completion time.
- GET/POST /api/v1/habits list or create owned routines with a cue, action, schedule, minimum version, and restart action. POST /api/v1/habits/{id}/check-ins records a dated completion or skip with an optional note; GET /api/v1/habits/{id}/check-ins returns history; PATCH /api/v1/habits/{id} pauses or resumes without deleting check-ins. Skips do not trigger a streak penalty, and later entries preserve corrections. Habit history is included in account export.
- GET/POST /api/v1/evidence list or add evidence. The public API records evidence as self-reported and unverified; callers cannot mark it verified.

All domain records are scoped to the signed-in account. API creation and changes require the session CSRF token. Dates use ISO calendar dates, and metric values retain their explicitly supplied units.

## THE CORE (initial read-only layer)

POST /api/v1/core/respond accepts an authenticated question and returns a response with context provenance and truncation metadata. It reads only the signed-in user's goals, tasks, habits, and evidence, with limits of 24 records and 6,000 context characters. The current deterministic fallback reports counts; it does not make generated recommendations. There are no tools or write actions. Provider selection and external data processing remain open; see docs/decisions/0002-core-provider-boundary.md.

## Planning and quests (initial preview)

GET /api/v1/plans/preview accepts a start date and a 1–31 day horizon. It returns the signed-in user's pending tasks in that window plus prompts for active goals without tasks. Results are deterministic previews: they are not saved, assigned XP, or dispatched as actions.

GET/PUT `/api/v1/daily-plans/{date}` reads or saves a per-day selection of owned tasks, available minutes, and energy. A plan cannot exceed its stated capacity. PATCH `/api/v1/daily-plans/{date}/items/{id}` records completion, deferral, or removal. GET `/api/v1/daily-plans/{date}/recovery` previews eligible unfinished actions from earlier plans. It never carries tasks forward automatically, changes a task without a user choice, or applies a missed-day penalty. Daily plan data is included in account export and removed with the account.

## Character build and progression

GET `/api/v1/rpg/status` returns the signed-in Hunter's rank, level, XP, achievements, starter rank thresholds, and ruleset version. A task awards 10 XP once while completed; reopening it appends an equal negative correction. Repeated same-status requests do not duplicate points. PATCH `/api/v1/rpg/character` changes the display name/callsign or pauses new awards. GET `/api/v1/rpg/events` reads the append-only ledger; POST `/api/v1/rpg/events/{id}/correct` appends a correction without deleting the original. Rank/XP values are editable starter rules and explicitly marked draft. `GET/POST/PATCH /api/v1/rpg/skills` creates user-defined skills; POST `/api/v1/rpg/skills/{id}/evidence` adds self-reported evidence that is never marked verified by the app. GET `/api/v1/rpg/chronicle` shows a recent, account-scoped history. No numerical Life Score or irreversible prestige reset is implemented.

## Domain progress intelligence

GET /api/v1/insights/progress compares a metric's current value with its baseline and target using `(current - baseline) / (target - baseline) * 100`. It preserves units and measurement source, returns no percentage when the baseline equals the target, and does not clamp values or make predictions. It is arithmetic only and makes no health or financial recommendations.

## Calendar and reminders

GET /api/v1/notifications/inbox lists pending tasks due from today through the next 31 days. GET /api/v1/calendar.ics downloads the signed-in account's dated tasks as iCalendar events. Both are read-only and account-scoped. The app does not send push/email notifications or sync with an external calendar.

## Bounded agent actions

POST `/api/v1/agent/proposals/next-task` remains a read-only preview. The UI action flow uses POST `/api/v1/agent/actions` to record one local task proposal against an owned active goal. POST `/api/v1/agent/actions/{id}/approve` creates that task only after a separate CSRF-protected approval; reject prevents creation. POST `/api/v1/agent/actions/{id}/undo` marks the created task skipped when it is still pending and has never been put in a daily plan. Approval is idempotent, the audit contains no prompt or task text, and action records are included in account export. This is a fixed local task tool, not free-form model execution; no code, shell, files, network, calendar, or financial actions are available.

## Voice controls

On the THE CORE screen, on-device dictation starts only after a tap and only if the browser confirms local recognition support for the selected language. The app never falls back to server-based speech recognition; on iPhone, use the keyboard microphone if local recognition is unavailable. The transcript is inserted as editable text and is not submitted until the user sends it. Read aloud is also user-triggered and uses the browser's speech synthesis. No recording is saved by LifeResets.

## Onboarding, campaigns, and reviews

GET/PATCH /api/v1/onboarding/awakening and /api/v1/onboarding/awakening/{step} provide seven one-at-a-time prompts with resumable status and optional answers. The 7-day cadence is encouraged but never blocks app use. Reflection answers require the latest `awakening_storage` consent grant, appear in account export, and can be removed with DELETE /api/v1/onboarding/awakening/answers; withdrawal blocks new answers. Awakening also returns account-owned numeric baselines and explicit unknown markers by life area. POST /api/v1/onboarding/awakening/baselines requires separate `assessment_baseline_storage` consent; every entry records its capture time, optional measurement date, unit, and confidence, and later entries preserve the earlier history. DELETE /api/v1/onboarding/awakening/baselines/{id} removes one entry, including after consent withdrawal. These values are exported and are not sent to an AI provider. The database is not encrypted at rest, so exact health or financial values require careful user choice. Baseline entries do not create goals or an overall score. POST/GET /api/v1/campaigns creates and lists 90-calendar-day campaigns; PATCH /api/v1/campaigns/{id} changes status. POST/GET /api/v1/reviews creates and lists weekly/monthly reviews with cadence-specific guided prompts; PATCH /api/v1/reviews/{id} saves answers or changes draft/completed status. The UI lets the user grant or withdraw `reflection_storage` consent. Review answers appear in export; DELETE /api/v1/reviews/{id}/responses removes them without deleting the review. Withdrawal blocks new answer writes but leaves existing answers until deleted. Lifecycle records are deleted with the account.

## Operations and safe evolution

The local runbook is [docs/operations.md](docs/operations.md); the project change gates are [docs/decisions/0003-safe-evolution.md](docs/decisions/0003-safe-evolution.md). Encrypted SQLite backup/restore is available through `python -m liferesets.backup`; PostgreSQL backups and automated retention remain unimplemented. Production hosting still requires monitoring, MFA, password recovery, and deployed rate limiting.

## Web/PWA interface

Open the API root (`/`) for the iPhone-first, installable app shell. The interface supports local sign-in/out, goal and action creation, capacity- and energy-aware daily planning, explicit recovery decisions, character and skill tracking, milestone history, voice controls, and browser-persisted display preferences. The service worker caches only static assets and never caches `/api/` responses. Offline data entry and push notifications are not enabled. Voice input requires a secure context and confirmed on-device recognition; the app does not fall back to cloud speech recognition.

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
