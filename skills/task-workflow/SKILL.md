---
name: task-workflow
description: >-
  End-to-end task design, implementation, and three-stage PR review workflow.
  Activate this skill whenever the user mentions, defines, or asks to work on a
  task (e.g., "Task 2: ...", or references a file in `tasks/`). Creates a
  dedicated git branch, drafts a design plan, spawns a Devil's Advocate subagent
  to grill the design, conducts an interactive design review with the user until
  accepted, implements the solution, runs an AI Security & Clean Code PR Reviewer
  subagent, presents the PR to the user for Human PR Review, runs a post-approval
  final AI PR Review upon `pr approved`, and only after both approvals moves the
  task into `tasks/done/`, rebases onto `master`, and pushes `master` to GitHub.
---

# Task Workflow (Branch -> Design -> Devil's Advocate -> Design Mode -> Implement -> AI PR Review -> Human PR Review -> Post-Approval AI PR Review -> Rebase & Done)

Follow these steps strictly in order whenever a task is mentioned or started. Do **not** skip ahead to implementation before the user accepts the design, and do **not** rebase/complete the task before the user approves the Human PR Review and the post-approval review passes.

---

## Step 1: Record Task & Create Git Branch

1. **Task File**: Ensure the task exists in `tasks/task_<number>_<short_slug>.md` using the simple format from `tasks/template.md`:
   ```markdown
   # Task <Number>: <Title>

   ## Objective
   <Brief description of what the task achieves.>

   ## Requirements
   - <Requirement 1>
   - <Requirement 2>
   ```
2. **Git Branch**: Create and switch to a new branch for the task:
   ```bash
   git checkout -b feat/task-<number>-<short-slug>
   ```

---

## Step 2: Draft Initial Design Plan

Inspect the codebase and draft a clear, concrete design plan covering:
- **Domain Models & Signatures**: Classes, dataclasses (`frozen=True`), function signatures, and exceptions to add or modify in `src/boardgamerules/`.
- **Clean Code & `# CONCEPT:` Alignment**: How the design preserves immutability, Command-Query Separation (CQS), Single Responsibility, and educational `# CONCEPT:` tags (`AGENTS.md`).
- **Planned Unit Tests**: Specific `test_should_<expected_result>_when_<condition>` test cases to write in `tests/`.

---

## Step 3: Spawn the Devil's Advocate Subagent (Grill the Plan)

Before presenting the plan to the user, challenge it with a dedicated **Devil's Advocate** subagent:

1. **Define & Invoke Subagent**:
   Use `define_subagent` (name: `devils-advocate`, `EnableWriteTools: false`) and `invoke_subagent` with `Role: "Devil's Advocate Reviewer"`:
   - Give the subagent the task requirements, relevant codebase context, and your proposed design plan.
   - Instruct the subagent to **argue against the design**, ruthlessly grilling it for:
     - Over-engineering, unnecessary abstractions, or bloated APIs
     - Violations of immutability, CQS, or Single Responsibility
     - Edge cases, invalid state transitions, or missing domain exceptions
     - Simpler, cleaner alternatives that achieve the same requirements
2. **Incorporate Feedback**:
   Wait for the Devil's Advocate critique. Refine the design plan to fix flaws exposed by the critique and note any genuine architectural trade-offs that require a decision from the user.

---

## Step 4: Enter Design Mode & Get User Acceptance

1. **Present Design & Critique Summary**:
   Present to the user:
   - The proposed architecture and file/symbol changes.
   - Key points raised by the **Devil's Advocate** and how the design addresses them.
   - Planned unit test scenarios.
2. **Model-Tier Handoff (Plan-Heavy -> Execute-Light)**:
   When the user asks to plan with a higher-tier model and switch to a lower-tier model for implementation:
   - Persist a self-contained **Technical Implementation Plan** directly into `tasks/task_<number>_<short_slug>.md` (after the Devil's Advocate refinement and/or user approval).
   - Include exact file paths, class/dataclass/function signatures, validation invariants, error-handling rules, logging fields, `# CONCEPT:` tags, stepdown/import conventions, and the exact list of unit test cases (`test_should_<expected>_when_<condition>`).
   - Provide a short copy-pasteable handoff prompt (e.g., `"Implement Task <N> following the Technical Implementation Plan in tasks/task_<number>_<short_slug>.md (Step 5 onwards)."`).
3. **Ask for Design Acceptance (`ask_question`)**:
   - If there are open trade-offs or design choices, use `ask_question` to resolve them with the user in interactive Design Mode.
   - Ask the user to confirm whether they **Accept the design** or want adjustments.
4. **Wait for Approval**:
   **STOP** and wait for the user's response. Do **not** write production or test code until the user accepts the design.

---

## Step 5: Implement & Verify

Once the user accepts the design:

1. **Write Tests First**: Implement unit tests in `tests/` following the AAA (Arrange-Act-Assert) pattern.
2. **Implement Solution**: Write clean, immutable code in `src/boardgamerules/` with `# CONCEPT:` annotations and run `uv run python scripts/collect_concepts.py`.
3. **Run Quality Checks**:
   ```bash
   uv run pytest
   uv run ruff check --fix .
   uv run ruff format .
   ```

---

## Step 6: Stage 1 — AI Subagent PR Review (Security & Clean Code)

1. **Spawn PR Reviewer Subagent**:
   Use `define_subagent` (name: `pr-reviewer`, `EnableWriteTools: false`) and `invoke_subagent` with `Role: "Security & Clean Code PR Reviewer"` to inspect all branch changes for **Security** and **Clean Code (`AGENTS.md`)**.
2. **Address Findings**:
   If `CHANGES_REQUESTED`, fix all findings, re-run `uv run pytest` and `uv run ruff check .`, and re-verify with the `pr-reviewer` subagent until `APPROVED`.

---

## Step 7: Stage 2 — Human PR Review (Wait for User Approval)

1. **Present PR for Human Review**:
   Once the initial AI `pr-reviewer` approves, present the completed changes, AI review takeaways, and clickable links to all modified files to the user.
2. **STOP and Wait for Explicit `pr approved`**:
   Do **NOT** move the task file to `tasks/done/`, commit, or rebase onto `master` until the user has reviewed the changes, had any questions or change requests resolved, and explicitly typed the phrase **`pr approved`**. Never treat general replies (`"proceed"`, `"is fine"`, `"ok"`, `"yes"`) during review discussions as final PR approval.

---

## Step 8: Stage 3 — Post-Approval Final AI PR Review

Immediately after the user explicitly types **`pr approved`**:
1. Run quality gate checks:
   ```bash
   uv run pytest
   uv run ruff check .
   ```
2. Spawn a fresh AI PR Reviewer subagent (`define_subagent` name: `pr-reviewer`, `EnableWriteTools: false`, `Role: "Security & Clean Code PR Reviewer"`) to perform a final inspection of all branch changes against `master`.
3. Verify that all changes (including any adjustments or fixes made during human review) remain clean, secure, and compliant with `AGENTS.md`.
4. Ensure the subagent returns `Verdict: APPROVED`. If any issues are found, resolve them and re-verify before proceeding.

---

## Step 9: Finalize — Move to `tasks/done/`, Rebase onto `master`, & Push to GitHub

Only after the user explicitly types **`pr approved`** AND the post-approval final AI PR review returns `APPROVED`:
1. Move `tasks/task_<number>_<short_slug>.md` into `tasks/done/` and update `tasks/README.md`.
2. Commit the changes on the feature branch, rebase onto `master`, fast-forward merge into `master`, delete the feature branch, and push `master` to GitHub (`git push origin master`).
