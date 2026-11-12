---
name: pr-review
description: >-
  Two-stage PR review workflow: (1) Spawns a dedicated AI PR Reviewer subagent
  focused on Security and Clean Code (AGENTS.md) and fixes any issues it finds;
  (2) Presents the changes to the user for Human PR Review (comments, questions,
  or change requests). Only after explicit human approval does it move the active
  task file into `tasks/done/`, commit, and rebase/merge onto `master`.
---

# Two-Stage PR Review (AI Reviewer -> Human Review -> Rebase & Archive)

## Step 1: Run Quality Gate Checks
Before invoking the reviewer subagent, ensure all automated checks pass:
```bash
uv run pytest
uv run ruff check .
```

## Step 2: Stage 1 — AI Security & Clean Code PR Reviewer Subagent
1. Define and invoke a read-only subagent (`define_subagent` name: `pr-reviewer`, `EnableWriteTools: false`, `Role: "Security & Clean Code PR Reviewer"`).
2. Prompt the subagent to review all changes on the current branch against `master` focusing on two pillars:
   - **Security**:
     - No hardcoded secrets, tokens, or API keys
     - Safe file/path handling (prevent path traversal, null bytes, control chars)
     - Input validation and safe query construction
     - Safe error handling that does not leak internal credentials or stack traces
   - **Clean Code (`AGENTS.md`)**:
     - Meaningful, intention-revealing names (verbs for functions, nouns for entities)
     - Small, single-responsibility functions with lean signatures (1–3 args)
     - Strict Command-Query Separation (CQS) and immutability (`@dataclass(frozen=True)`)
     - Domain-specific exceptions instead of silent `None`/`False` returns
     - Educational `# CONCEPT:` tags synchronized with `CONCEPTS.md`
     - Fast, isolated AAA unit tests with `test_should_<expected>_when_<condition>` naming
3. If the subagent returns `Verdict: CHANGES_REQUESTED`: fix every reported issue, re-run `uv run pytest` and `uv run ruff check .`, and re-verify with the `pr-reviewer` subagent via `send_message` until it returns `Verdict: APPROVED`.

## Step 3: Stage 2 — Human PR Review (Wait for User Approval)
Once the AI `pr-reviewer` subagent approves:
1. Present a concise **PR Review Summary** to the user with:
   - Clickable links to all created/modified files and key symbols.
   - Summary of what the AI PR Reviewer caught and fixed.
   - Any `# CONCEPT:` highlights added in this task.
2. **STOP and wait for the user's Human PR Review**:
   - Do **NOT** move the task to `tasks/done/`, commit, or rebase onto `master` yet.
   - Invite the user to inspect the code, ask questions, comment, or request changes.
   - If the user requests changes or asks questions, address them and wait until the user explicitly approves the PR.

## Step 4: Finalize — Move Task to `tasks/done/` & Rebase onto `master`
Only after the user explicitly approves the Human PR Review:
1. Move the completed task markdown file into `tasks/done/`:
   ```bash
   mkdir -p tasks/done
   git mv tasks/task_<number>_<short_slug>.md tasks/done/task_<number>_<short_slug>.md
   ```
2. Update `tasks/README.md` to list the task under `Completed Tasks`.
3. Commit, rebase onto `master`, and fast-forward `master`:
   ```bash
   git add -A
   git commit -m "feat(task-<number>): <summary>"
   git rebase master
   git checkout master
   git merge --ff-only feat/task-<number>-<short-slug>
   ```
