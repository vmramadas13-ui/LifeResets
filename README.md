# LifeResets

LifeResets is a private, adaptive personal operating system for turning goals into measurable actions. Development follows the staged build sequence and acceptance gates in the master blueprint.

## Current stage

The repository contains the initial Python package scaffold and a basic health check. API, database, identity, and product features have not been built yet.

## Requirements

- Git
- Python 3.12
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

## Set up locally

From the repository root, create the project environment and install the exact dependencies recorded in `uv.lock`:

```bash
uv sync --locked --all-groups
```

The project virtual environment is created at `.venv/`. Use `uv run` for project commands so they run in that environment.

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

Do not commit `.env` files, credentials, or personal exports. `.env.example` is the safe template for documented configuration; no application settings are needed yet.

## Project layout

```text
.github/workflows/  Continuous integration
src/liferesets/     Python application package
tests/              Automated tests
```
