# Tasks

Each task is defined in a concise markdown file with an **Objective** and **Requirements** list (see [`template.md`](template.md)).

## Format
```markdown
# Task <Number>: <Title>

## Objective
Implement reusable components shared across modules.

## Requirements
- Create ...
- Store ...
- Add tests for ...
```

## Workflow
When a task is mentioned, the [`task-workflow`](../skills/task-workflow/SKILL.md) skill runs automatically:
1. Create `tasks/task_<number>_<short_slug>.md` and checkout branch `feat/task-<number>-<short-slug>`.
2. Draft a design plan and challenge it with a **Devil's Advocate** subagent.
3. Review the design and Devil's Advocate feedback with the user in **Design Mode** until accepted.
4. Implement the solution and unit tests, then verify with `uv run pytest` and `uv run ruff check .`.
