# BoardGameRules

An AI-powered **Board Game Rulebook RAG & Assistant Platform** that resolves board game rules via a 3-tier pipeline (`Indexed RAG` $\rightarrow$ `Internet API Fetch + RAG` $\rightarrow$ `AI Fallback Generation`), generates Quick Recaps, answers grounded rulebook questions with page citations, and saves user history.

## Documentation & Links
- **[DESIGN.md](DESIGN.md)**: Architecture, technology stack, and recorded engineering decisions.
- **[CONCEPTS.md](CONCEPTS.md)**: Auto-collected glossary of `[AI Engineering]`, `[System Design]`, and `[Design Pattern]` `# CONCEPT:` annotations across the codebase.
- **[AGENTS.md](AGENTS.md)**: Engineering standards, Clean Code principles, and task workflow.
- **[tasks/README.md](tasks/README.md)**: Active task backlog and completed tasks (`tasks/done/`).

## Quick Commands (`uv`)
```bash
# Run unit tests
uv run pytest

# Run Ruff linter & formatter check
uv run ruff check .
uv run ruff format --check .

# Update or verify CONCEPTS.md glossary
uv run python scripts/collect_concepts.py
uv run python scripts/collect_concepts.py --check
```
