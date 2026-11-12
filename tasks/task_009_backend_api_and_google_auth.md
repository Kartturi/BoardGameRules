# Task 9: Backend HTTP API & Google OAuth Login

## Objective
Expose the application capabilities via a REST API (FastAPI) with Google OAuth authentication.

## Requirements
- Define Pydantic v2 request/response DTO schemas in `src/boardgamerules/api/` mapped cleanly to and from domain dataclasses.
- Implement Google OAuth 2.0 login / token verification AND a zero-config `dev_local` login mode so the app works locally on `localhost` without requiring Google Cloud credentials.
- Persist `UserProfile` in the NoSQL database.
- Create endpoints for searching/selecting a game, viewing rules, generating a Quick Recap, asking RAG questions, and saving/listing user history.
- Create an admin/upload endpoint to drop a PDF manual into the pending ingestion queue.
- Add API integration tests covering authentication and core endpoints.
