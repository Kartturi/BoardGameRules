# Task 12: GitHub Actions CI Pipeline

## Objective
Create an automated GitHub Actions Continuous Integration (CI) workflow to verify linting, formatting, `# CONCEPT:` glossary synchronization, and unit tests on every push and pull request.

## Requirements
- Create `.github/workflows/ci.yml` triggered on `push` (to `master` and `feat/**`) and `pull_request`.
- Use `astral-sh/setup-uv` with dependency caching and Python 3.14.
- Run quality gates in CI: `ruff check .`, `ruff format --check .`, `collect_concepts.py` drift check, and `pytest`.
- Enforce least-privilege GitHub token permissions (`contents: read`) and concurrency cancellation for outdated runs on the same branch.
