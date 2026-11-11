---
name: task-workflow
description: >-
  End-to-end task design and implementation workflow. Activate this skill whenever
  the user mentions, defines, or asks to work on a task (e.g., "Task 2: ...", or
  references a file in `tasks/`). Creates a dedicated git branch, drafts a design
  plan, spawns a Devil's Advocate subagent to grill and challenge the design,
  conducts an interactive design review with the user until accepted, and then
  implements and verifies the solution.
---

# Task Workflow (Branch -> Design -> Devil's Advocate -> Design Mode -> Implement)

Follow these steps strictly in order whenever a task is mentioned or started. Do **not** skip ahead to implementation before the user explicitly accepts the design.

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
- **Clean Code Alignment**: How the design preserves immutability, Command-Query Separation (CQS), and Single Responsibility (`AGENTS.md`).
- **Planned Unit Tests**: Specific `test_should_<expected_result>_when_<condition>` test cases to write in `tests/`.

---

## Step 3: Spawn the Devil's Advocate Subagent (Grill the Plan)

Before presenting the plan to the user, challenge it with a dedicated **Devil's Advocate** subagent:

1. **Define or Invoke Subagent**:
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
   Present to the user (via a design artifact or structured response):
   - The proposed architecture and file/symbol changes.
   - Key points raised by the **Devil's Advocate** and how the design addresses them.
   - Planned unit test scenarios.
2. **Ask for Design Acceptance (`ask_question`)**:
   - If there are open trade-offs or design choices, use `ask_question` to resolve them with the user in interactive Design Mode.
   - Ask the user to confirm whether they **Accept the design** or want adjustments.
3. **Wait for Approval**:
   **STOP** and wait for the user's response. Do **not** write production or test code until the user accepts the design. If the user requests changes, update the design and re-confirm.

---

## Step 5: Implement & Verify

Once the user accepts the design:

1. **Write Tests First**: Implement unit tests in `tests/` following the AAA (Arrange-Act-Assert) pattern.
2. **Implement Solution**: Write clean, immutable domain/engine code in `src/boardgamerules/`.
3. **Run Quality Checks**:
   ```bash
   uv run pytest
   uv run ruff check --fix .
   uv run ruff format .
   ```
4. **Report Completion**: Summarize the implemented changes and verification results with clickable file links.
