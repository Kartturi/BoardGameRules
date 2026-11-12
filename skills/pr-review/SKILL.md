---
name: pr-review
description: >-
  Spawns a dedicated PR Reviewer subagent focused on Security and Clean Code
  (AGENTS.md). When approved, moves the active task file into `tasks/done/`,
  commits the changes, and rebases/merges the branch onto `master`. Activate
  when asked to review a PR/branch or complete a task.
---

# PR Review, Rebase to `master`, and Archive Task (`tasks/done/`)

## Step 1: Run Quality Gate Checks
Before invoking the reviewer subagent, ensure all automated checks pass:
```bash
uv run pytest
uv run ruff check .
```

## Step 2: Spawn the Security & Clean Code PR Reviewer Subagent
1. Define and invoke a read-only subagent (`define_subagent` name: `pr-reviewer`, `EnableWriteTools: false`, `Role: "Security & Clean Code PR Reviewer"`).
2. Prompt the subagent to review all changes on the current branch against `master` (`git status` and `git diff master`) focusing on two pillars:
   - **Security**:
     - No hardcoded secrets, tokens, or API keys
     - Safe file/path handling (prevent path traversal on PDF filenames/uploads)
     - Input validation and safe query construction (prevent NoSQL/prompt/command injection)
     - Safe error handling that does not leak internal credentials or stack traces
   - **Clean Code (`AGENTS.md`)**:
     - Meaningful, intention-revealing names (verbs for functions, nouns for entities)
     - Small, single-responsibility functions with lean signatures (1–3 args)
     - Strict Command-Query Separation (CQS) and immutability (`@dataclass(frozen=True)`)
     - Domain-specific exceptions instead of silent `None`/`False` returns
     - Fast, isolated AAA unit tests with `test_should_<expected>_when_<condition>` naming
3. Require the subagent to output a structured review with `Verdict: APPROVED` or `Verdict: CHANGES_REQUESTED`.

## Step 3: Resolve Review Feedback
- If `Verdict: CHANGES_REQUESTED`: fix every reported issue, re-run `uv run pytest` and `uv run ruff check .`, and send the updated diff back to the `pr-reviewer` subagent via `send_message` until it responds with `Verdict: APPROVED`.

## Step 4: Move Task to `tasks/done/` & Rebase onto `master`
Once approved:
1. Move the completed task markdown file into `tasks/done/`:
   ```bash
   mkdir -p tasks/done
   git mv tasks/task_<number>_<short_slug>.md tasks/done/task_<number>_<short_slug>.md
   ```
2. Update `tasks/README.md` links if applicable.
3. Commit, rebase onto `master`, and fast-forward `master`:
   ```bash
   git add -A
   git commit -m "feat(task-<number>): <summary>"
   git rebase master
   git checkout master
   git merge --ff-only feat/task-<number>-<short-slug>
   ```
