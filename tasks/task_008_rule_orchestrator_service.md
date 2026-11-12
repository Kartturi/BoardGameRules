# Task 8: Rule Orchestrator ("Organisation Body")

## Objective
Implement the central orchestrator service that coordinates the 3-tier rule resolution pipeline (`RAG -> Internet API + RAG -> AI Fallback`).

## Requirements
- Resolve game rule requests in strict priority order:
  1. Check if the game manual is already indexed in the RAG system / NoSQL DB.
  2. If missing, invoke the Internet API Fetcher; if found, ingest into RAG and return.
  3. If internet fetch fails, invoke the AI Fallback module to generate the rules.
- Coordinate Quick Recap generation and specific rule Q&A against the active game.
- Allow users to save generated rules, recaps, and Q&A answers into their NoSQL user history.
- Add unit tests covering all 3 resolution paths and failure fallbacks.
