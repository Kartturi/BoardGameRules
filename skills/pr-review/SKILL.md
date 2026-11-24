---
name: pr-review
description: >-
  Three-stage PR review workflow: (1) Spawns an initial AI PR Reviewer subagent
  focused on Security and Clean Code (AGENTS.md) and fixes any issues it finds;
  (2) Presents the changes to the user for Human PR Review (comments, questions,
  or change requests); (3) Upon explicit human approval (`pr approved`), runs a
  post-approval final AI PR Review to verify the final diff against `master` before
  moving the active task file into `tasks/done/`, committing, rebasing/merging onto `master`,
  and pushing `master` to GitHub.
---

# Three-Stage PR Review (Pre-Review -> Human Review -> Post-Approval Review -> Rebase & Archive)

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
     - Centralized logging compliance (`logging.getLogger(__name__)` with `extra={...}` in I/O/service modules, no `print()` for operational logs, no logging in pure `domain/`, log errors once at the boundary, never log secrets/PII)
     - Educational `# CONCEPT:` tags synchronized with `CONCEPTS.md`
     - Fast, isolated AAA unit tests with `test_should_<expected>_when_<condition>` naming
3. If the subagent returns `Verdict: CHANGES_REQUESTED`: fix every reported issue, re-run `uv run pytest` and `uv run ruff check .`, and re-verify with the `pr-reviewer` subagent via `send_message` until it returns `Verdict: APPROVED`.

## Step 3: Stage 2 — Human PR Review (Wait for User Approval)
Once the initial AI `pr-reviewer` subagent approves:
1. Present a concise **PR Review Summary** to the user with:
   - Clickable links to all created/modified files and key symbols.
   - Summary of what the AI PR Reviewer caught and fixed.
   - Any `# CONCEPT:` highlights added in this task.
2. **STOP and wait for the user's Human PR Review (`pr approved`)**:
   - Do **NOT** move the task to `tasks/done/`, commit, or rebase onto `master` yet.
   - Invite the user to inspect the code, ask questions, comment, or request changes.
   - **Strict Approval Trigger**: Only treat the PR as approved when the user explicitly types **`pr approved`**. Never treat general acknowledgments (`"proceed"`, `"is fine"`, `"ok"`, `"yes"`) to intermediate questions or code tweaks as final PR approval.

## Step 4: Stage 3 — Post-Approval Final AI PR Review
Immediately after the user explicitly types **`pr approved`**:
1. Run quality gate checks:
   ```bash
   uv run pytest
   uv run ruff check .
   ```
2. Spawn a fresh AI PR Reviewer subagent (`define_subagent` name: `pr-reviewer`, `EnableWriteTools: false`, `Role: "Security & Clean Code PR Reviewer"`) to perform a final inspection of all branch changes against `master`.
3. Verify that all changes (including any adjustments or fixes made during human review) remain clean, secure, and compliant with `AGENTS.md`.
4. Ensure the subagent returns `Verdict: APPROVED`. If any issues are found, resolve them and re-verify before proceeding.

## Step 5: Finalize — Move Task to `tasks/done/`, Rebase onto `master`, & Push to GitHub
Only after human approval (`pr approved`) AND the post-approval final AI PR review returns `APPROVED`:
1. Move the completed task markdown file into `tasks/done/`:
   ```bash
   mkdir -p tasks/done
   git mv tasks/task_<number>_<short_slug>.md tasks/done/task_<number>_<short_slug>.md
   ```
2. Update `tasks/README.md` to list the task under `Completed Tasks`.
3. Commit, rebase onto `master`, fast-forward `master`, delete the feature branch, and push `master` to GitHub:
   ```bash
   git add -A
   git commit -m "feat(task-<number>): <summary>"
   git rebase master
   git checkout master
   git merge --ff-only feat/task-<number>-<short-slug>
   git branch -d feat/task-<number>-<short-slug>
   git push origin master
   ```
