# Agent Guidelines & Engineering Standards

Welcome to **BoardGameRules**. This repository is built using AI-assisted development. All contributors and AI assistants must adhere to the principles and workflows outlined below.

---

## 1. Core Engineering Principles (Modern Clean Code)

The primary goal is **high human readability and maintainability**. Code is read far more often than it is written.

### 1.1 Meaningful Names & High Readability
- **Intention-revealing**: Names must explain *why* something exists, *what* it does, and *how* it should be used.
  - Good: `active_player`, `remaining_deck_count`, `validate_card_play()`
  - Bad: `p`, `cnt`, `check()`, `temp_data`
- **Verbs for actions, nouns for entities**:
  - Functions/methods are actions: `advance_turn()`, `draw_card()`, `is_game_over()`
  - Classes and variables are nouns: `TurnTracker`, `GameBoard`, `winning_score`
- **Avoid cryptic abbreviations**: Favor clarity over saving a few keystrokes.

### 1.2 Small, Focused Functions (Single Responsibility)
- Each function should do **one thing well**.
- If a function has multiple levels of abstraction, extract sub-steps into helper functions with descriptive names.
- Keep function signatures lean (typically 1 to 3 arguments). Group related arguments into dedicated dataclasses if needed.

### 1.3 Command-Query Separation (CQS)
- **Queries** return data and must not produce side effects.
- **Commands** perform an action or state transition and should not return complex query results unexpectedly.

### 1.4 Immutability & Pure Logic
- Prefer immutable domain models using `@dataclass(frozen=True)` or Pydantic where appropriate.
- Prefer pure functions that take the current game state and an action, returning a new game state rather than mutating state in place.
- Keep domain logic completely separated from I/O (file system, network, terminal prints).

### 1.5 Self-Documenting Code & Minimal Comments
- Let the code structure, type hints, and naming do the talking.
- **No redundant comments or noisy docstrings**: Do not add docstrings or inline comments to functions, methods, or properties whose name and signature already explain what they do.
- **No meta-references in code**: Never reference `AGENTS.md`, "Clean Code principles", or task numbers inside source code comments or docstrings.
- Aside from `# CONCEPT:` tags and brief module docstrings, only write a comment when explaining a non-obvious *why* or a tricky edge case.

### 1.6 Explicit Error Handling
- Define domain-specific exceptions (e.g., `InvalidMoveError`, `RuleViolationError`, `TurnOrderError`).
- Fail fast and provide meaningful, user-friendly error messages. Avoid returning `None` or silent boolean `False` when an operation is invalid.

### 1.7 Educational Concept Tags (`# CONCEPT:`)
- Because this is a learning and practice project, annotate key architectural, AI engineering, system design, and design pattern usages directly in the code using structured `# CONCEPT:` comments:
  ```python
  # CONCEPT: [Design Pattern] Interface Segregation Principle (ISP)
  # Splitting a monolithic repository into focused protocols so clients only depend
  # on the methods they actually use.
  ```
- Categories to highlight:
  - `[AI Engineering]` (e.g., RAG chunking, vector embeddings, grounded generation, fallback pipelines, citation attribution)
  - `[System Design]` (e.g., stateless compute, blob storage abstraction, idempotency, eventual consistency)
  - `[Design Pattern]` (e.g., Repository, Strategy, Facade, Protocol/Structural Subtyping, Value Object, Immutable State Transition)
- These `# CONCEPT:` tags are also indexed in `CONCEPTS.md` so they can be browsed in one place.

---

## 2. Test-Always Philosophy

Every piece of functionality must be verified by automated tests.

1. **Test-First / Spec-Driven**: Write tests alongside or before the implementation.
2. **AAA Pattern**: Structure tests with clear phases:
   - **Arrange**: Set up game state and players.
   - **Act**: Execute the rule or action.
   - **Assert**: Verify the expected outcome and state change.
3. **Descriptive Test Names**:
   - `test_should_<expected_result>_when_<condition>`
   - Example: `test_should_raise_error_when_player_plays_out_of_turn`
4. **Fast & Isolated**: Unit tests in `tests/unit` must run in milliseconds and have zero external dependencies.

---

## 3. Task-Driven Workflow (`tasks/`)

Tasks are kept lightweight and focused in `tasks/` (see `tasks/template.md`).

### Task Format
```markdown
# Task <Number>: <Title>

## Objective
<Brief description of what the task achieves.>

## Requirements
- <Requirement 1>
- <Requirement 2>
```

### Workflow (`task-workflow` & `pr-review` Skills)
Whenever a task is mentioned, always activate and follow [`skills/task-workflow/SKILL.md`](skills/task-workflow/SKILL.md):
1. **Branch & Define**: Ensure `tasks/task_<number>_<short_slug>.md` is created and checkout a new branch (`feat/task-<number>-<short-slug>`).
2. **Design Plan**: Draft the technical design and planned test cases.
3. **Devil's Advocate**: Spawn a Devil's Advocate subagent to critically grill and argue against the design plan; refine the plan based on its findings.
4. **Design Mode & Approval**: Present the design and Devil's Advocate critique to the user, resolve trade-offs interactively, and wait for explicit user acceptance before coding.
5. **Implement & Verify**: Implement tests (`tests/`) and code (`src/boardgamerules/`), then run `uv run pytest` and `uv run ruff check .`.
6. **AI PR Review ([`skills/pr-review/SKILL.md`](skills/pr-review/SKILL.md))**: Spawn a separate PR Reviewer subagent focusing on **Security** and **Clean Code**, and resolve any findings until approved.
7. **Human PR Review & Approval**: Present the PR summary and changed files to the user for human review, comments, or adjustments. Wait for explicit user approval.
8. **Finalize, Rebase & Done**: Once the user approves the PR, move the task file into `tasks/done/`, commit, and rebase/merge onto `master`.

---

## 4. Toolchain & Quality Checks

- **Language**: Python 3.14+
- **Package & Env Manager**: `uv`
- **Linter & Formatter**: `ruff`
- **Test Framework**: `pytest`

### Essential Commands
```bash
# Run tests
uv run pytest

# Check code style & lint issues
uv run ruff check .

# Automatically fix lint issues and format
uv run ruff check --fix .
uv run ruff format .
```
