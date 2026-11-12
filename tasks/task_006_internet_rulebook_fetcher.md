# Task 6: Internet API Rulebook Fetcher Module

## Objective
Implement the API fetching module that searches for and downloads official board game rulebooks from the internet when a game is not yet in the RAG system.

## Requirements
- Search external board game / rulebook sources (e.g., BoardGameGeek API / web search) for a requested game title.
- Download discovered PDF or text rulebooks and validate their content before ingestion.
- Return structured rulebook content ready for the RAG module to index.
- Add unit tests with mocked HTTP responses for found, missing, and invalid rulebook downloads.
