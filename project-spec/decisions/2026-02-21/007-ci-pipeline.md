# Decision: CI pipeline with GitHub Actions

**Date:** 2026-02-21
**Status:** Accepted

## Context

No CI/CD exists. With a test suite being added (decision 006), we need automated test runs on push/PR to prevent regressions.

## Decision

### Pipeline: GitHub Actions

Single workflow file: `.github/workflows/ci.yml`

**Jobs:**

1. **lint** — runs on every push and PR.
   - `ruff check` (linting)
   - `ruff format --check` (formatting)
   - `pyright` or `mypy` (type checking) — choose one; pyright is faster and works well with Pydantic.

2. **test** — runs on every push and PR, after lint.
   - Matrix: Python 3.13 (single version for now; expand if needed).
   - `uv sync --dev` to install dependencies.
   - `pytest tests/unit/ --cov=src/mcp_deck_server --cov-report=xml` for unit tests.
   - Upload coverage artifact.

3. **integration** (optional) — manual trigger or on `main` only.
   - Requires `NC_URL`, `NC_USER`, `NC_APP_PASSWORD` as GitHub Actions secrets.
   - `pytest tests/integration/ -m integration`
   - Only runs when secrets are available (skip gracefully otherwise).

4. **benchmarks** (optional) — on `main` only or manual trigger.
   - `pytest tests/benchmarks/`
   - Informational — does not block merge.

### Tooling added to dev dependencies

- `ruff` (lint + format)
- `pyright` (type checking)
- `pytest`, `pytest-asyncio`, `pytest-cov`, `respx` (testing — from decision 006)

### Pre-commit (optional, not blocking)

Consider `pre-commit` with ruff hooks for local dev experience. Not required for CI.

## Consequences

- Every push and PR gets lint + unit test validation.
- Integration tests protect `main` without blocking feature PRs.
- `pyproject.toml` needs `[project.optional-dependencies]` or `[dependency-groups]` for dev deps.
- GitHub Actions secrets needed for integration tests.
