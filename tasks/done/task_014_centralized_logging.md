# Task 14: Centralized Structured Logging

## Objective
Set up a zero-dependency, centralized logging module using Python's standard `logging` library with dual output formats (`console` for local development and GCP Cloud Logging-compatible `json` on `stdout` for Cloud Run), add meaningful logging across existing I/O modules, and establish a permanent logging standard in `AGENTS.md` and `skills/pr-review/SKILL.md` for all future code.

## Requirements
- Create a centralized logging configuration module (e.g., `src/boardgamerules/logging_config.py`) configured via `LOG_LEVEL` (default `INFO`) and `LOG_FORMAT` (`console` or `json`, default `console`).
- Support a human-readable `console` formatter for local development and a single-line GCP Cloud Logging-compatible `json` formatter emitting `severity`, `message`, `logger`, `timestamp`, exception tracebacks, and safe structured `extra` fields to `stdout`.
- Explain how standard streams (`stdout`/`stderr`) integrate with GCP Cloud Logging using plain-English `# CONCEPT:` tags synced to `CONCEPTS.md`.
- Wire `configure_logging()` into application entrypoints (`src/boardgamerules/batch/cli.py`, `main.py`) and document `LOG_LEVEL` and `LOG_FORMAT` in `.env.example`.
- Add meaningful, secret-safe logging across existing I/O and orchestration modules (`batch/`, `rag/`, `db/`) while keeping pure `domain/` models free of logging side effects.
- Update `AGENTS.md` and `skills/pr-review/SKILL.md` so all future tasks and PR reviews enforce the centralized logging standard.
- Verify formatters, log level filtering, structured extra fields, and exception formatting with fast, isolated unit tests in `tests/unit/`.
