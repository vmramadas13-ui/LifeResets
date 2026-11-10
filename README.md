# LifeResets

LifeResets is a private, adaptive personal operating system for turning goals into measurable actions. This repository is being built in small, verified stages; the master blueprint defines the product scope, architecture, safety rules, and acceptance gates.

## Current stage

The repository currently contains the initial Python package scaffold and a basic health check. API, database, identity, and product features have not been built yet.

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Git

## Set up locally

From the repository root, run:

```bash
uv sync --all-groups
```

This creates or updates the project virtual environment from `uv.lock`, including development tools.

## Run checks

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## Project layout

```text
src/liferesets/   Python application package
tests/            Automated tests
.github/workflows/ci.yml  Continuous integration checks
```

Keep secrets and personal exports out of Git. Local environment files, virtual environments, and Python cache files should remain untracked.
