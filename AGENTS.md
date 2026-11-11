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

### 1.5 Self-Documenting Code & Clean Comments
- Let code structure and naming tell the story.
- Do not write comments that describe *what* the code does (that is redundant).
- Use comments only to document *why* a particular decision was made or to explain specific board game official rule references.

### 1.6 Explicit Error Handling
- Define domain-specific exceptions (e.g., `InvalidMoveError`, `RuleViolationError`, `TurnOrderError`).
- Fail fast and provide meaningful, user-friendly error messages. Avoid returning `None` or silent boolean `False` when an operation is invalid.

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

### Workflow (`task-workflow` Skill)
Whenever a task is mentioned, always activate and follow [`skills/task-workflow/SKILL.md`](skills/task-workflow/SKILL.md):
1. **Branch & Define**: Ensure `tasks/task_<number>_<short_slug>.md` is created and checkout a new branch (`feat/task-<number>-<short-slug>`).
2. **Design Plan**: Draft the technical design and planned test cases.
3. **Devil's Advocate**: Spawn a Devil's Advocate subagent to critically grill and argue against the design plan; refine the plan based on its findings.
4. **Design Mode & Approval**: Present the design and Devil's Advocate critique to the user, resolve trade-offs interactively, and wait for explicit user acceptance before coding.
5. **Implement & Verify**: Implement tests (`tests/`) and code (`src/boardgamerules/`), then run `uv run pytest` and `uv run ruff check .`.

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
